from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path


SUPPORTED_SUFFIXES = {
    # JavaScript / TypeScript
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    # Python
    ".py", ".pyi",
    # JVM
    ".java", ".kt", ".kts", ".scala",
    # Systems
    ".go", ".rs", ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
    # Ruby / PHP / Swift
    ".rb", ".php", ".swift",
    # C#
    ".cs",
    # Shell / config
    ".sh", ".bash",
    # Lua / Dart
    ".lua", ".dart",
}
DEFAULT_IGNORED_DIRS = {
    ".codeviz",
    ".git",
    ".venv",
    "venv",
    ".env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "vendor",
    "fixtures",
    ".next",
    ".nuxt",
    "target",
    "out",
    ".idea",
    ".vscode",
    "coverage",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "egg-info",
}


def _load_gitignore_patterns(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return []
    patterns: list[str] = []
    for raw_line in gitignore.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _matches_gitignore(rel_path: str, patterns: list[str]) -> bool:
    matched = False
    for pattern in patterns:
        negated = pattern.startswith("!")
        candidate = pattern[1:] if negated else pattern
        is_dir_pattern = candidate.endswith("/")
        normalized = candidate.rstrip("/")
        did_match = False
        if is_dir_pattern:
            did_match = rel_path == normalized or rel_path.startswith(f"{normalized}/")
        else:
            did_match = fnmatch.fnmatch(rel_path, candidate) or fnmatch.fnmatch(Path(rel_path).name, candidate)
        if did_match:
            matched = not negated
    return matched


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    patterns = _load_gitignore_patterns(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(part in DEFAULT_IGNORED_DIRS or part.endswith(".egg-info") for part in path.parts):
            continue
        if _matches_gitignore(rel, patterns):
            continue
        if path.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(path)
    return files


LANGUAGE_MAP = {
    ".ts": "typescript", ".tsx": "typescriptreact",
    ".js": "javascript", ".jsx": "javascriptreact", ".mjs": "javascript", ".cjs": "javascript",
    ".py": "python", ".pyi": "python",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    ".go": "go", ".rs": "rust",
    ".c": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".cs": "csharp",
    ".sh": "shell", ".bash": "shell",
    ".lua": "lua", ".dart": "dart",
}


def detect_language(path: Path) -> str:
    return LANGUAGE_MAP.get(path.suffix.lower(), "unknown")


def compute_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in iter_source_files(root):
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        digest.update(rel.encode("utf-8"))
        digest.update(str(stat.st_size).encode("utf-8"))
        digest.update(str(int(stat.st_mtime_ns)).encode("utf-8"))
    return digest.hexdigest()

