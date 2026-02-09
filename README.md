# Contextual Architect

> **An AI system that writes production-grade, enterprise-ready code by learning from project evolution and enforcing architectural compliance via multi-agent orchestration.**

## 🎯 The Innovation

Current AI coding tools (Cursor, Copilot, Replit) write code that works in isolation but fails enterprise code review. **Contextual Architect** is different:

| Existing Tools | Contextual Architect |
|----------------|---------------------|
| Isolated code snippets | Full project-aware features |
| No pattern learning | Learns from PR evolution data |
| Single model | Multi-agent swarm (Historian, Architect, Implementer, Reviewer) |
| Static context | Real-time codebase context via MCP |

## 📦 Project Structure

```
contextual-architect/
├── data_pipeline/              # Phase 1: Data Collection
│   └── src/
│       ├── pr_evolution/       # Custom PR extractor ✅
│       └── codereviewer/       # Microsoft dataset downloader ✅
├── training/                   # Phase 2: Model Fine-tuning
├── agents/                     # Phase 3: Multi-Agent Swarm ⭐ Core Innovation
├── mcp_servers/                # Phase 3: MCP Integrations
└── security/                   # Phase 4: Security Layer
```

## 🚀 Quick Start

### 1. Setup
```bash
cd data_pipeline
python -m venv venv
.\venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Download Training Data
```bash
# Option A: Use Microsoft CodeReviewer dataset (recommended)
python -m src.codereviewer --output data/codereviewer/

# Option B: Extract from specific repos (supplementary)
$env:GITHUB_TOKEN="your_token"
python -m src.pr_evolution --repo gofiber/fiber --output data/custom/
```

## 📊 Progress

- [x] Phase 1A: CodeReviewer dataset integration
- [x] Phase 1B: Custom PR extractor (with quality scoring)
- [ ] Phase 2: Model fine-tuning (QLoRA)
- [ ] **Phase 3: Multi-Agent MCP Architecture** ⭐ Core Innovation
- [ ] Phase 4: Security layer
- [ ] Phase 5: Testing & validation

## 🧠 Tech Stack

| Layer | Technology |
|-------|------------|
| Data Pipeline | Python (PyGithub, requests) |
| Orchestrator | Go (goroutines for parallel agents) |
| MCP Servers | TypeScript |
| Training | PyTorch, QLoRA |
| Base Model | DeepSeek-Coder / CodeReviewer |

## 📄 Research & Prior Art

- **Microsoft CodeReviewer**: [Paper](https://arxiv.org/abs/2203.09095) | [Dataset](https://zenodo.org/record/6900648)
- Our contribution: Multi-agent architecture + MCP integration + real-time codebase awareness

## 📄 License

MIT License - See [LICENSE](LICENSE)

## 👤 Author

**Yuvraj Sharma** - B.Tech 2nd Year
