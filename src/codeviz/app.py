from __future__ import annotations

import argparse
from pathlib import Path

from codeviz.commands import run_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codeviz")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("open", "analyze", "reanalyze", "ask"):
        sub = subparsers.add_parser(name)
        sub.add_argument("project", type=Path)
        sub.add_argument("query", nargs="?")
        sub.add_argument("--port", type=int, default=None)
        sub.add_argument("--no-browser", action="store_true")
        sub.add_argument("--json", action="store_true", dest="json_output")

    setup = subparsers.add_parser("setup")
    setup.add_argument("project", type=Path, nargs="?", default=Path("."))

    return parser


def run_cli(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_command(args)
