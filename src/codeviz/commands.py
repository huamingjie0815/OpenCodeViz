from __future__ import annotations

import json
import sys
import time
from argparse import Namespace
from pathlib import Path

from codeviz.project import CodeVizProject


def run_command(args: Namespace) -> None:
    if args.command == "setup":
        _run_setup(Path(args.project).resolve())
        return

    project = CodeVizProject(Path(args.project).resolve())

    if args.command == "analyze":
        result = project.run_live_analysis(
            port=args.port,
            open_browser=not args.no_browser,
        )
    elif args.command == "reanalyze":
        result = project.run_live_analysis(
            port=args.port,
            open_browser=not args.no_browser,
        )
    elif args.command == "open":
        result = project.open(port=args.port, open_browser=not args.no_browser)
    elif args.command == "ask":
        result = project.ask(args.query or "")
    else:
        raise ValueError(f"unknown command: {args.command}")

    if args.json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(_human_output(args.command, result))
        if result.get("ok") is False:
            raise SystemExit(1)

    if args.command in {"open", "analyze", "reanalyze"} and sys.stdout.isatty() and not args.json_output:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return


PROVIDERS = {
    "1": ("openai", "gpt-4o-mini"),
    "2": ("anthropic", "claude-sonnet-4-20250514"),
    "3": ("google_genai", "gemini-2.0-flash"),
}


def _run_setup(project_root: Path) -> None:
    config_dir = project_root / ".codeviz"
    config_path = config_dir / "config.json"

    existing: dict = {}
    if config_path.exists():
        existing = json.loads(config_path.read_text(encoding="utf-8"))

    print("CodeViz Setup")
    print("=" * 40)

    # Provider
    print("\nLLM Provider:")
    print("  1) OpenAI (default: gpt-4o-mini)")
    print("  2) Anthropic (default: claude-sonnet-4-20250514)")
    print("  3) Google GenAI (default: gemini-2.0-flash)")
    current_provider = existing.get("provider", "openai")
    choice = input(f"\nSelect provider [1/2/3] (current: {current_provider}): ").strip()
    if choice in PROVIDERS:
        provider, default_model = PROVIDERS[choice]
    else:
        provider = current_provider
        default_model = PROVIDERS.get("1", ("", ""))[1]
        for _, (p, m) in PROVIDERS.items():
            if p == provider:
                default_model = m
                break

    # Model
    current_model = existing.get("model", default_model)
    model = input(f"Model name (current: {current_model}): ").strip() or current_model

    # API Key
    current_key = existing.get("apiKey", "")
    masked = current_key[:4] + "****" + current_key[-4:] if len(current_key) > 8 else "(not set)"
    key_input = input(f"API Key [{masked}]: ").strip()
    api_key = key_input if key_input else current_key

    # Base URL
    current_base_url = existing.get("baseUrl", "")
    base_url_input = input(f"Base URL (current: {current_base_url or 'default'}): ").strip()
    base_url = base_url_input if base_url_input else current_base_url

    # Port
    current_port = existing.get("port", "")
    port_input = input(f"Web port (current: {current_port or 'auto'}): ").strip()
    port = int(port_input) if port_input.isdigit() else current_port

    config = {**existing, "provider": provider, "model": model}
    if api_key:
        config["apiKey"] = api_key
    if base_url:
        config["baseUrl"] = base_url
    elif "baseUrl" in config and not base_url:
        del config["baseUrl"]
    if port:
        config["port"] = port

    config_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nConfig saved to {config_path}")
    print(f"  provider: {provider}")
    print(f"  model:    {model}")
    print(f"  apiKey:   {'****' if api_key else '(not set)'}")
    if base_url:
        print(f"  baseUrl:  {base_url}")
    if port:
        print(f"  port:     {port}")


def _human_output(command: str, result: dict) -> str:
    lines: list[str] = []
    if command in {"analyze", "reanalyze"}:
        lines.append(f"Mode: {command}")
        lines.append(f"State: {result.get('reuse_state', '-')}")
        summary = result.get("summary", {})
        lines.append(
            f"Graph: files={summary.get('files', 0)} entities={summary.get('entities', 0)} edges={summary.get('edges', 0)}"
        )
        open_payload = result.get("open")
        if isinstance(open_payload, dict):
            lines.append(f"URL: {open_payload.get('url', '-')}")
        if result.get("analysis_started"):
            lines.append("Live analysis started.")
    elif command == "open":
        if result.get("ok") is False:
            lines.append(result.get("error", "Unknown error"))
        else:
            lines.append("Mode: open")
            lines.append(f"State: {result.get('reuse_state', '-')}")
            lines.append(f"URL: {result.get('url', '-')}")
    elif command == "ask":
        lines.append(f"Source: {result.get('source_scope', '-')}")
        lines.append(result.get("answer", ""))
    return "\n".join(lines)
