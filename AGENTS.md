# AGENTS.md

## MCP Configuration

For this project, Codex/OMX should load project MCP servers from [.codex/config.toml](/Users/hmj/Desktop/project/show-your-code/.codex/config.toml) using `[mcp_servers.*]`.

This repository does not use `.mcp.json` for Codex MCP loading. Do not assume Codex will auto-load MCP servers from `.mcp.json` in this repository.

When adding or updating MCP servers for Codex in this project:

1. Edit `.codex/config.toml`.
2. Keep `.codex/config.toml` as the single source of truth for project MCP servers.
3. Restart the Codex session after MCP config changes if the new servers do not appear in the current session.

## Local Rules

### Output

- Return code first. Explanation after, only if non-obvious.
- No inline prose.
- Use comments sparingly, only where logic is unclear.
- No boilerplate unless explicitly requested.

### Code Rules

- Simplest working solution. No over-engineering.
- No abstractions for single-use operations.
- No speculative features or "you might also want..."
- Read the file before modifying it. Never edit blind.
- No docstrings or type annotations on code not being changed.
- No error handling for scenarios that cannot happen.
- Three similar lines is better than a premature abstraction.

### Review Rules

- State the bug. Show the fix. Stop.
- No suggestions beyond the scope of the review.
- No compliments on the code before or after the review.

### Debugging Rules

- Never speculate about a bug without reading the relevant code first.
- State what you found, where, and the fix. One pass.
- If cause is unclear, say so. Do not guess.

### Simple Formatting

- No em dashes, smart quotes, or decorative Unicode symbols.
- Plain hyphens and straight quotes only.
- Natural language characters (accented letters, CJK, etc.) are fine when the content requires them.
- Code output must be copy-paste safe.

### Approach

- Think before acting. Read existing files before writing code.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files you have already read unless the file may have changed.
- Test your code before declaring done.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override this file.
