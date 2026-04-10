from pathlib import Path

from codeviz.fingerprint import compute_fingerprint, iter_source_files


def test_fingerprint_changes_when_source_changes(tmp_path: Path) -> None:
    (tmp_path / "main.ts").write_text("export function alpha() { return 1; }\n", encoding="utf-8")
    first = compute_fingerprint(tmp_path)
    (tmp_path / "main.ts").write_text("export function alpha() { return 2; }\n", encoding="utf-8")
    second = compute_fingerprint(tmp_path)
    assert first != second


def test_iter_source_files_respects_default_ignored_directories(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("export const ok = 1;\n", encoding="utf-8")
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "sample.ts").write_text("export const fixture = 1;\n", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("export const bundle = 1;\n", encoding="utf-8")

    files = [path.relative_to(tmp_path).as_posix() for path in iter_source_files(tmp_path)]

    assert files == ["src/main.ts"]


def test_iter_source_files_respects_gitignore(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("export const ok = 1;\n", encoding="utf-8")
    (tmp_path / "ignored.ts").write_text("export const ignored = 1;\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.ts\n", encoding="utf-8")

    files = [path.relative_to(tmp_path).as_posix() for path in iter_source_files(tmp_path)]

    assert files == ["src/main.ts"]
