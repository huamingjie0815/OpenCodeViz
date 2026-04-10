from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

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
"""


class ProjectQAAgent:
    def __init__(self, root: Path, status: ProjectStatus, config: dict):
        self.root = root
        self.status = status
        self.config = config

    def ask(self, question: str, session_id: str = "project-default") -> dict:
        context = self._build_context(question, session_id)

        if create_deep_agent is not None and self._has_api_key():
            return self._ask_via_agent(question, context)

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
                parts.append(f"- [{e['entity_type']}] {e['name']} in {e['file_path']}:{e['start_line']} -- {e.get('description', '')}")
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

    def _ask_via_agent(self, question: str, context: str) -> dict:
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
        result = agent.invoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"recursion_limit": 100},
        )

        answer = ""
        if isinstance(result, dict):
            messages = result.get("messages", [])
            if messages:
                last = messages[-1]
                content = last.get("content", "") if isinstance(last, dict) else getattr(last, "content", str(last))
                if isinstance(content, list):
                    answer = " ".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in content
                    )
                else:
                    answer = str(content)
        elif hasattr(result, "content"):
            answer = str(result.content)
        else:
            answer = str(result)

        return {"answer": answer, "citations": [], "model": model, "provider": provider}

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

        @tool
        def search_code_entities(query: str) -> str:
            """Search for code entities (classes, functions, methods) in the project by name or keyword."""
            results = search_entities(status, query, limit=15)
            return json.dumps(results, ensure_ascii=False)

        @tool
        def get_entity_detail(entity_id: str) -> str:
            """Get detailed information about a specific code entity and its connected relationships."""
            data = get_entity_neighbors(status, entity_id)
            return json.dumps(data, ensure_ascii=False)

        @tool
        def search_project_docs(query: str) -> str:
            """Search project documentation (README, specs, design docs) by keyword."""
            results = search_documents_by_query(status, query, limit=8)
            return json.dumps(results, ensure_ascii=False)

        @tool
        def read_source_file(file_path: str, start_line: int = 1, end_line: int = 50) -> str:
            """Read source code from a file. Provide relative file path and optional line range."""
            full_path = root / file_path
            if not full_path.exists():
                return f"File not found: {file_path}"
            if not full_path.is_relative_to(root):
                return "Access denied: path outside project root"
            try:
                lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
                start = max(0, start_line - 1)
                end = min(len(lines), end_line)
                selected = lines[start:end]
                numbered = [f"{i+start_line}: {line}" for i, line in enumerate(selected)]
                return "\n".join(numbered)
            except Exception as exc:
                return f"Error reading file: {exc}"

        @tool
        def get_project_overview() -> str:
            """Get a high-level overview of the project including name, description, languages, and key files."""
            info = load_project_info(status)
            if info is None:
                return "No project info available. Run analysis first."
            return json.dumps(info.to_dict(), ensure_ascii=False)

        @tool
        def get_call_graph(entity_id: str) -> str:
            """Trace the call graph for an entity - who calls it and what it calls."""
            data = get_entity_neighbors(status, entity_id)
            return json.dumps(data, ensure_ascii=False)

        return [
            search_code_entities,
            get_entity_detail,
            search_project_docs,
            read_source_file,
            get_project_overview,
            get_call_graph,
        ]
