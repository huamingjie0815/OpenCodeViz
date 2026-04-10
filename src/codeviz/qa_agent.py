from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from codeviz.models import ProjectStatus
from codeviz.runtime_config import runtime_api_key, runtime_value
from codeviz.storage import (
    get_entity_neighbors,
    load_chat_session,
    load_documents,
    load_edges,
    load_entities,
    load_project_info,
    search_documents_by_query,
    search_entities,
)

try:
    from deepagents import create_deep_agent
except ImportError:
    create_deep_agent = None


QA_SYSTEM_PROMPT = """\
You are the project Q&A agent for an analyzed code repository.
Answer like a strong senior engineer who deeply understands this codebase.

You have access to tools that let you search code entities, read source files, \
search documentation, and explore the call graph.

Rules:
- Read the provided project context before answering
- Give a direct conclusion first, then cite concrete file paths and line numbers
- Use tools to look up specific details when needed
- Answer in the same language as the user's question
- If the evidence is partial, say what is confirmed and what is uncertain
- Be conservative: do not guess beyond the available evidence
- When citing code, use format: file_path:line_number

Efficiency:
- Minimize tool calls: prefer one broad search over multiple narrow ones
- Do not re-search for information already present in the project context above
- Once you have enough evidence, answer immediately -- do not make extra tool calls
- Batch related lookups when possible
- Never repeat the same tool call with the same arguments
- Aim to finish within 8 tool calls; if evidence is incomplete, answer with uncertainty instead of looping
"""

DEFAULT_QA_RECURSION_LIMIT = 40
DEFAULT_QA_TOOL_BUDGET = 8
DEFAULT_QA_SEARCH_LIMIT = 8
DEFAULT_QA_NEIGHBOR_LIMIT = 6
DEFAULT_QA_READ_LINE_LIMIT = 80


class QAAgentExecutionError(RuntimeError):
    pass


class ProjectQAAgent:
    def __init__(self, root: Path, status: ProjectStatus, config: dict):
        self.root = root
        self.status = status
        self.config = config

    def ask(self, question: str, session_id: str = "project-default", on_step: Callable[[dict], None] | None = None) -> dict:
        context = self._build_context(question, session_id)

        if create_deep_agent is not None and self._has_api_key():
            return self._ask_via_agent(question, context, on_step=on_step)

        return self._fallback_answer(question, context)

    def _has_api_key(self) -> bool:
        return bool(runtime_api_key(self.config))

    def _build_context(self, question: str, session_id: str) -> str:
        parts: list[str] = []

        # Project overview
        info = load_project_info(self.status)
        if info:
            parts.append(f"## Project: {info.name}")
            parts.append(f"Description: {info.description}")
            if info.languages:
                parts.append(f"Languages: {', '.join(info.languages)}")
            if info.readme_summary:
                parts.append(f"README summary: {info.readme_summary}")
            if info.spec_summary:
                parts.append(f"Spec summary: {info.spec_summary}")
            parts.append("")

        # Relevant entities
        entity_hits = search_entities(self.status, question, limit=15)
        if entity_hits:
            parts.append("## Relevant code entities:")
            for e in entity_hits:
                desc = (e.get('description', '') or '')[:100]
                parts.append(f"- [{e['entity_type']}] {e['name']} in {e['file_path']}:{e['start_line']} -- {desc}")
            parts.append("")

        # Relevant docs
        doc_hits = search_documents_by_query(self.status, question, limit=5)
        if doc_hits:
            parts.append("## Relevant documents:")
            for d in doc_hits:
                parts.append(f"- {d['file_path']}: {d['heading']} -- {d['excerpt'][:200]}")
            parts.append("")

        # Recent chat history
        history = load_chat_session(self.status, session_id)
        if history:
            parts.append("## Recent conversation:")
            for turn in history[-6:]:
                parts.append(f"User: {turn.get('question', '')}")
                if turn.get("answer"):
                    parts.append(f"Assistant: {turn['answer'][:300]}")
            parts.append("")

        return "\n".join(parts)

    def _ask_via_agent(self, question: str, context: str, on_step: Callable[[dict], None] | None = None) -> dict:
        from langchain.chat_models import init_chat_model

        provider = runtime_value("CODEVIZ_PROVIDER", self.config.get("provider", "openai"))
        model = runtime_value("CODEVIZ_MODEL", self.config.get("model", ""))
        api_key = runtime_api_key(self.config)
        base_url = runtime_value("CODEVIZ_BASE_URL", self.config.get("baseUrl", ""))

        if not model:
            model = {
                "openai": "gpt-4o-mini",
                "anthropic": "claude-sonnet-4-20250514",
                "google_genai": "gemini-2.0-flash",
            }.get(provider, "gpt-4o-mini")

        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google_genai": "GOOGLE_API_KEY",
        }
        env_var = env_map.get(provider)
        if api_key and env_var and not os.environ.get(env_var):
            os.environ[env_var] = api_key

        kwargs: dict = {"model_provider": provider}
        if base_url:
            kwargs["base_url"] = base_url
        llm = init_chat_model(model, **kwargs)

        tools = self._build_tools()

        agent = create_deep_agent(
            model=llm,
            tools=tools,
            instructions=QA_SYSTEM_PROMPT,
        )

        prompt = (
            f"Project context:\n{context}\n\n"
            f"User question: {question}"
        )

        def _emit(step: dict) -> None:
            if on_step is not None:
                on_step(step)

        _emit({"type": "thinking", "summary": "Analyzing question..."})

        try:
            recursion_limit = self._runtime_int(
                "CODEVIZ_QA_RECURSION_LIMIT",
                self.config.get("qaRecursionLimit", DEFAULT_QA_RECURSION_LIMIT),
                DEFAULT_QA_RECURSION_LIMIT,
                minimum=10,
                maximum=100,
            )
            stream = agent.stream(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"recursion_limit": recursion_limit},
            )
            last_messages = []
            for chunk in stream:
                messages = self._collect_stream_messages(chunk)
                for msg in messages:
                    self._emit_step_from_message(msg, _emit)
                    last_messages.append(msg)

            answer = self._extract_answer(last_messages)
            if not answer:
                raise QAAgentExecutionError("Agent returned no final answer")
        except Exception as exc:
            _emit({"type": "error", "summary": f"Agent error: {exc}"})
            if isinstance(exc, QAAgentExecutionError):
                raise
            raise QAAgentExecutionError(f"Agent execution failed: {exc}") from exc

        return {"answer": answer, "citations": [], "model": model, "provider": provider}

    @staticmethod
    def _runtime_int(name: str, configured: Any, default: int, minimum: int, maximum: int) -> int:
        raw = runtime_value(name, str(configured if configured not in (None, "") else default))
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _compact_entity_result(result: dict) -> dict:
        return {
            "entity_id": result.get("entity_id", ""),
            "entity_type": result.get("entity_type", ""),
            "name": result.get("name", ""),
            "file_path": result.get("file_path", ""),
            "start_line": result.get("start_line", 0),
            "end_line": result.get("end_line", 0),
            "signature": str(result.get("signature", ""))[:160],
            "description": str(result.get("description", ""))[:160],
        }

    @staticmethod
    def _compact_document_result(result: dict) -> dict:
        return {
            "doc_id": result.get("doc_id", ""),
            "file_path": result.get("file_path", ""),
            "heading": result.get("heading", ""),
            "start_line": result.get("start_line", 1),
            "end_line": result.get("end_line", 1),
            "excerpt": str(result.get("excerpt", ""))[:220],
        }

    @classmethod
    def _compact_neighbors(cls, data: dict, limit: int) -> dict:
        entity = data.get("entity") or {}
        outgoing = data.get("outgoing", [])[:limit]
        incoming = data.get("incoming", [])[:limit]
        return {
            "entity": cls._compact_entity_result(entity) if entity else None,
            "outgoing": [
                {
                    "edge_type": item.get("edge", {}).get("edge_type", ""),
                    "line": item.get("edge", {}).get("line", 0),
                    "target": cls._compact_entity_result(item.get("target") or {}),
                }
                for item in outgoing
            ],
            "incoming": [
                {
                    "edge_type": item.get("edge", {}).get("edge_type", ""),
                    "line": item.get("edge", {}).get("line", 0),
                    "source": cls._compact_entity_result(item.get("source") or {}),
                }
                for item in incoming
            ],
        }

    @staticmethod
    def _tool_budget_message(tool_name: str, remaining_budget: int) -> str:
        return json.dumps(
            {
                "warning": f"Tool budget reached before calling {tool_name}.",
                "remaining_budget": remaining_budget,
                "instruction": "Answer using the evidence you already have. Do not call more tools.",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _duplicate_call_message(tool_name: str, args: dict) -> str:
        return json.dumps(
            {
                "warning": f"Duplicate tool call blocked: {tool_name}",
                "arguments": args,
                "instruction": "Reuse the previous result instead of repeating the same tool call.",
            },
            ensure_ascii=False,
        )

    @classmethod
    def _collect_stream_messages(cls, payload: Any) -> list[Any]:
        if payload is None:
            return []
        if isinstance(payload, dict):
            if "messages" in payload:
                return cls._collect_stream_messages(payload["messages"])
            if cls._is_message_like(payload):
                return [payload]

            messages: list[Any] = []
            for value in payload.values():
                messages.extend(cls._collect_stream_messages(value))
            return messages

        if isinstance(payload, (list, tuple)):
            messages: list[Any] = []
            for item in payload:
                messages.extend(cls._collect_stream_messages(item))
            return messages

        if hasattr(payload, "messages"):
            return cls._collect_stream_messages(getattr(payload, "messages"))

        if cls._is_message_like(payload):
            return [payload]

        return []

    @staticmethod
    def _is_message_like(payload: Any) -> bool:
        if isinstance(payload, dict):
            return any(key in payload for key in ("content", "tool_calls", "role", "type"))
        return any(hasattr(payload, attr) for attr in ("content", "tool_calls", "role", "type"))

    @staticmethod
    def _stringify_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [ProjectQAAgent._stringify_content(item) for item in content]
            return " ".join(part for part in parts if part).strip()
        if isinstance(content, dict):
            if "text" in content:
                return str(content.get("text", ""))
            if "content" in content:
                return ProjectQAAgent._stringify_content(content.get("content"))
            return ""
        if hasattr(content, "text"):
            return str(getattr(content, "text", ""))
        return str(content)

    @staticmethod
    def _emit_step_from_message(msg: Any, emit: Callable[[dict], None]) -> None:
        ts = datetime.now(UTC).isoformat()
        if isinstance(msg, dict):
            role = msg.get("type", msg.get("role", ""))
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
        else:
            role = getattr(msg, "type", getattr(msg, "role", ""))
            content = getattr(msg, "content", "")
            tool_calls = getattr(msg, "tool_calls", [])

        if role == "ai" and tool_calls:
            for tc in tool_calls:
                name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                summary = f"Calling {name}"
                if name == "read_source_file" and args.get("file_path"):
                    summary = f"Reading {args['file_path']}"
                elif name == "search_code_entities" and args.get("query"):
                    summary = f"Searching entities: {args['query']}"
                elif name == "search_project_docs" and args.get("query"):
                    summary = f"Searching docs: {args['query']}"
                elif name == "get_entity_detail" and args.get("entity_id"):
                    summary = f"Inspecting entity: {args['entity_id']}"
                elif name == "get_call_graph" and args.get("entity_id"):
                    summary = f"Tracing call graph: {args['entity_id']}"
                emit({"type": "tool_call", "summary": summary, "tool": name, "timestamp": ts})
        elif role == "tool":
            name = msg.get("name", "") if isinstance(msg, dict) else getattr(msg, "name", "")
            emit({"type": "tool_result", "summary": f"Got result from {name}", "tool": name, "timestamp": ts})
        elif role == "ai" and content and not tool_calls:
            emit({"type": "thinking", "summary": "Composing answer...", "timestamp": ts})

    @staticmethod
    def _extract_answer(messages: list) -> str:
        for msg in reversed(messages):
            if isinstance(msg, dict):
                role = msg.get("type", msg.get("role", ""))
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls", [])
            else:
                role = getattr(msg, "type", getattr(msg, "role", ""))
                content = getattr(msg, "content", "")
                tool_calls = getattr(msg, "tool_calls", [])

            if role == "ai" and content and not tool_calls:
                answer = ProjectQAAgent._stringify_content(content)
                if answer:
                    return answer
        return ""

    def _fallback_answer(self, question: str, context: str) -> dict:
        return {
            "answer": (
                "deepagents is not available or no API key configured. "
                "Here is the retrieved context:\n\n" + context
            ),
            "citations": [],
        }

    def _build_tools(self) -> list:
        from langchain_core.tools import tool

        status = self.status
        root = self.root
        search_limit = self._runtime_int(
            "CODEVIZ_QA_SEARCH_LIMIT",
            self.config.get("qaSearchLimit", DEFAULT_QA_SEARCH_LIMIT),
            DEFAULT_QA_SEARCH_LIMIT,
            minimum=3,
            maximum=15,
        )
        neighbor_limit = self._runtime_int(
            "CODEVIZ_QA_NEIGHBOR_LIMIT",
            self.config.get("qaNeighborLimit", DEFAULT_QA_NEIGHBOR_LIMIT),
            DEFAULT_QA_NEIGHBOR_LIMIT,
            minimum=2,
            maximum=12,
        )
        read_line_limit = self._runtime_int(
            "CODEVIZ_QA_READ_LINE_LIMIT",
            self.config.get("qaReadLineLimit", DEFAULT_QA_READ_LINE_LIMIT),
            DEFAULT_QA_READ_LINE_LIMIT,
            minimum=20,
            maximum=200,
        )
        tool_budget = self._runtime_int(
            "CODEVIZ_QA_TOOL_BUDGET",
            self.config.get("qaToolBudget", DEFAULT_QA_TOOL_BUDGET),
            DEFAULT_QA_TOOL_BUDGET,
            minimum=3,
            maximum=20,
        )
        tool_state = {"calls": 0, "seen": set()}

        def _guard_tool_call(tool_name: str, args: dict) -> str | None:
            normalized_args = json.loads(json.dumps(args, ensure_ascii=False, sort_keys=True, default=str))
            cache_key = f"{tool_name}:{json.dumps(normalized_args, ensure_ascii=False, sort_keys=True)}"
            if cache_key in tool_state["seen"]:
                return self._duplicate_call_message(tool_name, normalized_args)
            if tool_state["calls"] >= tool_budget:
                return self._tool_budget_message(tool_name, max(tool_budget - tool_state["calls"], 0))
            tool_state["seen"].add(cache_key)
            tool_state["calls"] += 1
            return None

        @tool
        def search_code_entities(query: str) -> str:
            """Search for code entities (classes, functions, methods) in the project by name or keyword."""
            blocked = _guard_tool_call("search_code_entities", {"query": query})
            if blocked is not None:
                return blocked
            results = search_entities(status, query, limit=search_limit)
            compact = [self._compact_entity_result(result) for result in results[:search_limit]]
            return json.dumps({"results": compact, "count": len(compact)}, ensure_ascii=False)

        @tool
        def get_entity_detail(entity_id: str) -> str:
            """Get detailed information about a specific code entity and its connected relationships."""
            blocked = _guard_tool_call("get_entity_detail", {"entity_id": entity_id})
            if blocked is not None:
                return blocked
            data = get_entity_neighbors(status, entity_id)
            compact = self._compact_neighbors(data, neighbor_limit)
            return json.dumps(compact, ensure_ascii=False)

        @tool
        def search_project_docs(query: str) -> str:
            """Search project documentation (README, specs, design docs) by keyword."""
            blocked = _guard_tool_call("search_project_docs", {"query": query})
            if blocked is not None:
                return blocked
            results = search_documents_by_query(status, query, limit=search_limit)
            compact = [self._compact_document_result(result) for result in results[:search_limit]]
            return json.dumps({"results": compact, "count": len(compact)}, ensure_ascii=False)

        @tool
        def read_source_file(file_path: str, start_line: int = 1, end_line: int = 50) -> str:
            """Read source code from a file. Provide relative file path and optional line range."""
            blocked = _guard_tool_call(
                "read_source_file",
                {"file_path": file_path, "start_line": start_line, "end_line": end_line},
            )
            if blocked is not None:
                return blocked
            full_path = (root / file_path).resolve()
            if not full_path.is_relative_to(root.resolve()):
                return "Access denied: path outside project root"
            if not full_path.exists():
                return f"File not found: {file_path}"
            try:
                lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
                start = max(0, start_line - 1)
                requested_end = max(start + 1, end_line)
                end = min(len(lines), start + read_line_limit, requested_end)
                selected = lines[start:end]
                numbered = [f"{start + i + 1}: {line}" for i, line in enumerate(selected)]
                prefix = ""
                if requested_end > end:
                    prefix = (
                        f"Note: output truncated to {read_line_limit} lines. "
                        f"Requested {start_line}-{requested_end}, returned {start + 1}-{end}.\n"
                    )
                return prefix + "\n".join(numbered)
            except Exception as exc:
                return f"Error reading file: {exc}"

        @tool
        def get_project_overview() -> str:
            """Get a high-level overview of the project including name, description, languages, and key files."""
            blocked = _guard_tool_call("get_project_overview", {})
            if blocked is not None:
                return blocked
            info = load_project_info(status)
            if info is None:
                return "No project info available. Run analysis first."
            return json.dumps(
                {
                    "name": info.name,
                    "description": info.description,
                    "languages": info.languages,
                    "key_files": info.key_files[:10],
                    "readme_summary": str(info.readme_summary)[:240],
                    "spec_summary": str(info.spec_summary)[:240],
                },
                ensure_ascii=False,
            )

        @tool
        def get_call_graph(entity_id: str) -> str:
            """Trace the call graph for an entity - who calls it and what it calls."""
            blocked = _guard_tool_call("get_call_graph", {"entity_id": entity_id})
            if blocked is not None:
                return blocked
            data = get_entity_neighbors(status, entity_id)
            compact = self._compact_neighbors(data, neighbor_limit)
            return json.dumps(compact, ensure_ascii=False)

        return [
            search_code_entities,
            get_entity_detail,
            search_project_docs,
            read_source_file,
            get_project_overview,
            get_call_graph,
        ]
