# Contextual Architect

> **An AI system that writes production-grade, enterprise-ready code by learning from project evolution (PRs, RFCs, Git history) and enforcing architectural compliance.**

## 🎯 Vision

Current AI coding tools write code that works in isolation but fails in enterprise environments. This project builds a "Virtual Staff Engineer" that:

1. **Learns from PR Evolution** - Trains on "original code → reviewer feedback → fixed code"
2. **Understands Architecture** - Uses multi-agent swarm to analyze project structure
3. **Enforces Compliance** - Validates code against company-specific patterns before output
4. **Connects via MCP** - Real-time context from VS Code, GitHub, and terminal

## 📦 Project Structure

```
contextual-architect/
├── data_pipeline/          # Phase 1: Data Collection
│   └── src/pr_evolution/   # PR Evolution Extractor ✅
├── training/               # Phase 2: Model Fine-tuning (Coming)
├── agents/                 # Phase 3: Multi-Agent Swarm (Coming)
├── mcp_servers/            # Phase 3: MCP Integrations (Coming)
└── security/               # Phase 4: Security Layer (Coming)
```

## 🚀 Quick Start

### 1. Setup Data Pipeline
```bash
cd data_pipeline
python -m venv venv
.\venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Set GitHub Token
```bash
$env:GITHUB_TOKEN="your_token_here"  # PowerShell
# export GITHUB_TOKEN="your_token_here"  # Bash
```

### 3. Extract PR Evolution Data
```bash
python -m src.pr_evolution --repo gofiber/fiber --output data/
```

## 📊 Current Progress

- [x] Phase 1.3: PR Evolution Extractor
- [ ] Phase 1.1: DSA Content Scraper
- [ ] Phase 1.2: Stack Overflow Scraper
- [ ] Phase 2: Model Training Pipeline
- [ ] Phase 3: Multi-Agent Architecture
- [ ] Phase 4: Security Layer

## 🧠 Tech Stack

| Layer | Technology |
|-------|------------|
| Data Pipeline | Python (PyGithub, tqdm) |
| Orchestrator | Go |
| MCP Servers | TypeScript |
| Training | PyTorch, QLoRA, RLHF |
| Base Model | DeepSeek-Coder |

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

## 👤 Author

**Yuvraj Sharma**
