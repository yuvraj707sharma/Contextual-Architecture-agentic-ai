# Issues & Roadmap -- MACRO

## Open Bugs

### BUG: Architect file naming
**Labels**: `bug`, `priority-high`

Architect always targets `feature.py` regardless of task. Should suggest descriptive names (e.g., `health.py`, `users.py`).

### BUG: CWE-89 false positive
**Labels**: `bug`, `priority-medium`

Evaluation harness CWE-89 regex flags f-string error messages as SQL injection. Need to refine pattern to only match actual SQL queries. This is a model behavior issue, not a code fix.

---

## Completed (This Sprint)

- [x] **Proactive conflict detection** — ClarificationHandler detects auth/framework/DB/language mismatches before planning
- [x] **Production environment detection** — Deployment platform, Dockerfile parsing, runtime version, IaC tools
- [x] **File writing wired into CLI** — MACRO now shows diff, asks permission, and writes files to disk
- [x] **Rich reasoning display** — Per-agent icons and colors in terminal output
- [x] **Scanner safety** — 5000-file cap + 5-second timeout prevents hangs on large directories
- [x] **CLI exit crash fix** — Clean exit on Ctrl+C and CancelledError
- [x] **Word-boundary keyword matching** — Prevents false positives ("next" ≠ "next.js")
- [x] **`--yes` flag** — Auto-approve all changes (like Gemini CLI's `--yolo`)

---

## Open Enhancements

### Shell command execution
**Labels**: `enhancement`, `priority-high`

Run `npm install`, `pytest`, `git commit` after file writes. Requires sandboxed subprocess executor with allowlist/blocklist.

### Multi-file generation
**Labels**: `enhancement`, `priority-high`

Currently generates one file per task. Complex tasks (like refactoring) need coordinated multi-file output.

### PyPI packaging
**Labels**: `enhancement`, `priority-high`

Publish as `macro-cli` for one-command install: `pip install macro-cli`.

### MCP Integration
**Labels**: `enhancement`, `priority-medium`

Connect agents to live environment via MCP servers:
- `filesystem-mcp`: read_file, list_directory, write_file
- `github-mcp`: search_prs, get_pr_diff, get_file
- `terminal-mcp`: run_command, get_output

### VS Code Extension
**Labels**: `enhancement`, `future`

Package as VS Code extension for real developer workflow integration.

---

## Roadmap

### Near-term (March 2026)
- [ ] Shell command execution (sandboxed)
- [ ] Publish to PyPI as `macro-cli`
- [ ] Run RAG evaluation with full benchmark
- [ ] Collect failure samples for fine-tuning

### Medium-term (Q2 2026)
- [ ] Model fine-tuning (QLoRA on failure cases)
- [ ] Multi-file generation support
- [ ] MCP integration
- [ ] Long-term memory (SimpleMem-inspired)

### Long-term
- [ ] VS Code extension
- [ ] SAST integration (semgrep/bandit)
- [ ] Sandboxed code execution
- [ ] Subagent task delegation
