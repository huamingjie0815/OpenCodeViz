from pathlib import Path

from codeviz.fingerprint import compute_fingerprint


def test_distinct_content_produces_distinct_fingerprints(tmp_path: Path) -> None:
    proj_a = tmp_path / "a"
    proj_b = tmp_path / "b"
    (proj_a / "src").mkdir(parents=True)
    (proj_b / "src").mkdir(parents=True)
    (proj_a / "src" / "auth.ts").write_text('export function login() { return "v1"; }\n', encoding="utf-8")
    (proj_b / "src" / "auth.ts").write_text('export function login() { return "v2"; }\n', encoding="utf-8")
    assert compute_fingerprint(proj_a) != compute_fingerprint(proj_b)

