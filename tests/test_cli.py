from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from codeviz.app import run_cli
from codeviz.server import CodeVizServer


def parse_stdout(capsys) -> str:
    return capsys.readouterr().out


def wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    assert predicate()


def test_analyze_cli_bootstraps_codeviz_dir(fixture_project: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", lambda self: {"ok": True, "url": "http://127.0.0.1:39127/", "port": 39127})
    run_cli(["analyze", str(fixture_project), "--no-browser"])
    out = parse_stdout(capsys)

    codeviz_dir = fixture_project / ".codeviz"
    assert codeviz_dir.exists()
    # Data now lives under versions/{run_id}/
    versions_dir = codeviz_dir / "versions"
    wait_for(lambda: any((versions_dir / d / "meta.json").exists() for d in versions_dir.iterdir()) if versions_dir.exists() else False)
    assert "Mode: analyze" in out


def test_open_cli_returns_local_url_without_browser(
    fixture_project: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(CodeVizServer, "start", lambda self: {"ok": True, "url": "http://127.0.0.1:39127/", "port": 39127})
    # First analyze so open has data to serve
    run_cli(["analyze", str(fixture_project), "--no-browser"])
    capsys.readouterr()  # discard analyze output
    # Wait for background analysis to write current.json
    codeviz_dir = fixture_project / ".codeviz"
    wait_for(lambda: (codeviz_dir / "current.json").exists())
    run_cli(["open", str(fixture_project), "--no-browser"])
    out = parse_stdout(capsys)

    assert "Mode: open" in out
    assert "URL: http://127.0.0.1:39127/" in out


def test_ask_cli_labels_scope(fixture_project: Path, capsys) -> None:
    run_cli(["ask", str(fixture_project), "how does login work?"])
    out = parse_stdout(capsys)

    assert "Source: agent" in out


def test_analyze_cli_can_skip_browser(fixture_project: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(CodeVizServer, "start", lambda self: {"ok": True, "url": "http://127.0.0.1:39127/", "port": 39127})
    run_cli(["analyze", str(fixture_project), "--no-browser"])
    out = parse_stdout(capsys)

    assert "Mode: analyze" in out


def test_analyze_cli_blocks_in_interactive_mode(fixture_project: Path, monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(CodeVizServer, "start", lambda self: {"ok": True, "url": "http://127.0.0.1:39127/", "port": 39127})
    thread = threading.Thread(target=run_cli, args=(["analyze", str(fixture_project), "--no-browser"],), daemon=True)
    thread.start()
    thread.join(timeout=0.3)

    assert thread.is_alive() is True
