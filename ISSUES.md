# Issues & Roadmap -- MACRO

## Open Bugs

### BUG: Architect file naming
**Labels**: `bug`, `priority-high`

Architect always targets `feature.py` regardless of task. Should suggest descriptive names (e.g., `health.py`, `users.py`).

### BUG: CWE-89 false positive
**Labels**: `bug`, `priority-medium`

Evaluation harness CWE-89 regex flags f-string error messages as SQL injection. Need to refine pattern to only match actual SQL queries. This is a model behavior issue, not a code fix.

---

## Open Enhancements

### Multi-file generation
**Labels**: `enhancement`, `priority-high`

Currently generates one file per task. Complex tasks (like refactoring) need coordinated multi-file output.

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
- [ ] File provisional patent
- [ ] Run RAG evaluation with full benchmark
- [ ] Collect failure samples for fine-tuning
- [ ] Publish to PyPI as `macro-cli`

### Medium-term (Q2 2026)
- [ ] Model fine-tuning (QLoRA on failure cases)
- [ ] SimpleMem-inspired persistent memory
- [ ] Multi-file generation support
- [ ] MCP integration

### Long-term
- [ ] VS Code extension
- [ ] SAST integration (semgrep/bandit)
- [ ] Sandboxed code execution
- [ ] Subagent task delegation
