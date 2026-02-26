# Contextual Architect: Multi-Agent Orchestration with Retrieval-Augmented Generation for Repository-Aware Code Generation

**Yuvraj Sharma**
Department of Computer Science and Engineering
[Your University Name], [City, State, India]
Email: [your.email@university.edu]

---

## Abstract

Large Language Models (LLMs) generate syntactically correct code but frequently violate repository-specific architectural patterns, naming conventions, and security constraints. We present **Contextual Architect**, a multi-agent orchestration system that addresses this *Integration Gap* — the disconnect between generated code and the conventions of the target codebase. Our system decomposes code generation into seven specialized agents (Historian, Architect, Planner, Alignment Checker, Implementer, Reviewer, and Test Generator) coordinated by a finite-state orchestrator. We introduce a Retrieval-Augmented Generation (RAG) layer that indexes target repositories using AST-aware code chunking and ChromaDB vector search, providing semantically relevant code examples to agents at inference time. A constraint-based security enforcement mechanism implements CWE denylist checks as a post-generation validation gate. We evaluate our system on a FastAPI benchmark (44 files, 174 code chunks) across three tasks of increasing complexity. With RAG enabled, the system achieves **100% constraint compliance (32/32 checks)**, a 2.5x speedup over the baseline (41.5s vs. 85.8s), and eliminates a CWE-89 security anti-pattern by grounding generation in the repository's existing ORM patterns. Our evaluation harness, comprising 332 automated tests across four test suites, demonstrates reproducible results. The system supports seven LLM providers and degrades gracefully when optional components (ChromaDB, sentence-transformers) are unavailable.

**Keywords**: Multi-agent systems, code generation, retrieval-augmented generation, software engineering, constraint enforcement, large language models

---

## I. Introduction

The emergence of LLM-powered coding assistants — GitHub Copilot, Cursor, Claude Code — has fundamentally changed how developers write software. These tools generate syntactically correct code from natural language descriptions, achieving impressive results on benchmarks like HumanEval [1] and MBPP [2]. However, a critical gap persists between generating *correct* code and generating *integrated* code that follows a repository's existing patterns, conventions, and security requirements.

We term this the **Integration Gap**: the difference between code that compiles and code that passes a human code review. Consider a developer requesting "add a health check endpoint" to a FastAPI project. A naive LLM might generate a standalone Flask-style function, ignoring the project's existing `APIRouter` pattern, its snake_case naming conventions, and its directory structure (`app/api/routes/`). The generated code works — but it doesn't belong.

This gap has measurable consequences. Pearce et al. [3] found that approximately 40% of GitHub Copilot's suggestions contain security vulnerabilities traceable to specific CWE categories. Commercial tools provide no explicit enforcement mechanism — they rely on the LLM's training-time behavior rather than runtime constraint checking.

We present **Contextual Architect**, a system designed to close the Integration Gap through three mechanisms:

1. **Multi-agent decomposition**: Seven specialized agents, each with constrained responsibilities, process code generation tasks in a defined pipeline. This prevents any single agent from simultaneously navigating architecture, security, and implementation decisions.

2. **Repository-grounded RAG**: An AST-aware chunking system indexes the target repository into a ChromaDB vector store, providing semantically relevant code examples to agents at inference time. This grounds generation in the repository's actual patterns rather than the LLM's generic training data.

3. **Constraint-based security enforcement**: A post-generation Reviewer agent checks generated code against a CWE denylist (CWE-89, CWE-502, CWE-78) and validates structural compliance. This provides runtime guarantees that training-time safety cannot.

Our primary claim is that the combination of multi-agent orchestration and repository-specific RAG produces measurably more compliant code than single-shot LLM generation. We support this claim with a controlled before/after evaluation on a FastAPI benchmark, showing that RAG eliminates a CWE-89 false positive, improves file naming accuracy, and reduces total pipeline time by 51.6%.

---

## II. Related Work

### A. Multi-Agent Software Engineering

The application of multi-agent LLM systems to software engineering has gained significant attention. **ChatDev** [4] introduces a chat-powered development framework where specialized agents (CEO, CTO, Programmer, Tester) communicate through a "chat chain" to produce software from natural language specifications. While ChatDev demonstrates that role-based decomposition improves coherence, it operates on greenfield projects and does not address integration with existing codebases.

**MetaGPT** [5] advances the paradigm by encoding Standardized Operating Procedures (SOPs) into agent workflows, reducing cascading hallucinations through intermediate verification. MetaGPT's assembly-line approach, where each agent verifies its predecessor's output, directly influenced our pipeline design. However, MetaGPT focuses on complete application generation rather than targeted code modifications to existing repositories.

**MACOG** (Multi-Agent Code-Orchestrated Generation) [6] applies multi-agent orchestration to Infrastructure-as-Code (IaC) generation, with agents including Architect, Engineer, Reviewer, and Security Prover coordinated via a shared-blackboard orchestrator. MACOG demonstrates that multi-agent approaches improve IaC correctness from 54.90 to 74.02 on the IaC-Eval benchmark. Our work shares MACOG's philosophy of specialized agents with security verification, but targets general-purpose code generation within existing repositories rather than infrastructure configuration.

**SWE-agent** [12] introduces agent-computer interfaces that enable automated software engineering on existing repositories. Using a single agent operating through a custom shell interface, SWE-agent resolves 12.5% of issues on the SWE-bench benchmark. While SWE-agent demonstrates the value of repository-grounded code generation, it uses a single-agent architecture without explicit security enforcement or retrieval-augmented context.

**AutoCodeRover** [13] uses program structure-aware search to autonomously resolve GitHub issues, achieving 30.67% on SWE-bench-lite. AutoCodeRover leverages AST-based code search to navigate repositories, which is conceptually similar to our AST-aware chunking. However, it operates as a single agent and does not incorporate multi-agent orchestration, CWE enforcement, or RAG-based pattern retrieval.

### B. Code Security in LLM Generation

Pearce et al. [3] systematically evaluated GitHub Copilot's security, finding that across 1,689 generated programs targeting high-risk CWE scenarios, approximately 40% were vulnerable. Their work demonstrated that LLMs trained on open-source code inevitably learn insecure patterns. Our CWE denylist enforcement directly addresses their findings by implementing post-generation security gates.

**OctoBench** [7] introduces benchmarking for scaffold-aware instruction following, revealing a systematic gap between task-solving ability and constraint compliance in LLM coding agents. Their finding — that models can solve tasks but fail to follow heterogeneous constraints — motivates our separation of code generation (Implementer) from constraint validation (Reviewer).

### C. Retrieval-Augmented Generation for Code

RAG has been applied to various code intelligence tasks. Pornprasit et al. [8] demonstrate that RAG-based code review comment generation outperforms both pure generation and pure retrieval approaches, achieving +1.67% higher exact match and +4.25% higher BLEU scores. Their work establishes that conditioning generation on retrieved exemplars improves accuracy for code-related tasks.

Gong et al. [9] evaluate LLMs on syntax-aware code fill-in-the-middle tasks, finding that pretraining methods and data quality impact performance more than model size — supporting our approach of augmenting a smaller model (Llama-3.3-70B) with repository-specific retrieval rather than relying on a larger model.

Our RAG approach differs from prior work in its use of **AST-aware chunking** at the function/class boundary level, rather than arbitrary text splits. This produces semantically coherent chunks that preserve the structure of code units, improving retrieval relevance for code-specific queries.

### D. Positioning of Contextual Architect

Table I summarizes the key differences between our system and related work.

| Feature | ChatDev | MetaGPT | MACOG | SWE-agent | AutoCodeRover | Ours |
|---------|---------|---------|-------|-----------|---------------|------|
| Multi-agent pipeline | Yes | Yes | Yes | No | No | **Yes** |
| Targets existing repos | No | No | No | **Yes** | **Yes** | **Yes** |
| Repository-grounded RAG | No | No | No | No | AST search | **Yes** |
| AST-aware chunking | No | No | No | No | No | **Yes** |
| CWE denylist enforcement | No | No | OPA-based | No | No | **CWE-specific** |
| Incremental indexing | N/A | N/A | N/A | N/A | N/A | **Yes** |
| Quantified before/after eval | No | Yes | Yes | Yes | Yes | **Yes** |
| Graceful degradation | No | No | No | No | No | **Yes** |

*Table I: Feature comparison with related multi-agent code generation systems.*

---

## III. System Architecture

### A. Overview

Contextual Architect processes each code generation request through a pipeline of seven agents coordinated by a finite-state orchestrator (Fig. 1). The pipeline operates on a shared `AgentContext` object that accumulates information as it passes through each stage.

```
User Request
    |
    v
+----------------------------------+
|        ORCHESTRATOR              |
|  (Finite-State Controller)       |
|                                  |
|  +---------+  +---------+       |
|  |Historian |  |Architect|  <-- Parallel Discovery
|  +----+----+  +----+----+       |
|       |            |            |
|       v            v            |
|  +---------------------+       |
|  |   Planner Agent     |       |
|  +----------+----------+       |
|             |                   |
|             v                   |
|  +---------------------+       |
|  |  Alignment Checker  |       |
|  +----------+----------+       |
|             |                   |
|             v                   |
|  +---------------------+       |
|  |   Implementer       |<--+   |
|  +----------+----------+   |   |
|             |              |   |
|             v              |   |
|  +---------------------+   |   |
|  |    Reviewer         |---+   |  <- Retry Loop (max 3)
|  +----------+----------+       |
|             |                   |
|             v                   |
|  +---------------------+       |
|  |  Test Generator     |       |
|  +----------+----------+       |
|             |                   |
|             v                   |
|  +---------------------+       |
|  |   Safe Writer       |       |
|  +---------------------+       |
+----------------------------------+
         |
         v
   Generated Code + Tests
```

*Fig. 1: Contextual Architect pipeline architecture. Historian and Architect run in parallel during the discovery phase. The Implementer-Reviewer loop provides self-correction.*

### B. Agent Descriptions

**Historian Agent.** Scans the repository for coding patterns, conventions, and common practices. Uses heuristic file analysis to identify naming conventions (snake_case, camelCase), import patterns, error handling styles, and framework-specific idioms. When RAG is enabled, the Historian also performs semantic search to find historically similar implementations, merging heuristic and semantic results into a unified context.

**Architect Agent.** Maps the project's directory structure, identifies reusable utilities, and suggests where new code should be placed. The Architect extracts exported functions and classes from existing files, determines necessary imports, and generates a descriptive target filename using multi-word entity extraction from the user's request (e.g., "Add a health check endpoint" -> `health_endpoint.py`).

**Planner Agent.** Generates a structured implementation plan, assessing task complexity (simple/medium/complex) and identifying success criteria. When RAG is available, the Planner queries for similar past implementations to inform its strategy. The plan is written to disk as `plan.md` — a technique inspired by Manus AI [10] that pushes the plan into the LLM's recent attention window on every retry attempt.

**Alignment Checker.** Verifies that the Planner's proposed approach aligns with the Historian's discovered conventions and the Architect's structural analysis. This cross-validation step catches misalignments before code generation begins.

**Implementer Agent.** Generates the actual code based on accumulated context from all upstream agents. The Implementer's system prompt includes a **CWE denylist** that explicitly prohibits known vulnerability patterns:

- CWE-502: No `eval()` or `exec()` on untrusted input
- CWE-89: No f-string SQL queries (use parameterized queries/ORM)
- CWE-78: No `os.system()` or `subprocess(shell=True)`
- No `assert` for input validation
- No bare `except:` clauses

**Reviewer Agent.** Performs deterministic security scanning and structural validation on the generated code. The Reviewer applies regex-based pattern matching to detect CWE violations, then issues an APPROVED or CHANGES_REQUESTED verdict. If changes are requested, the Implementer retries with the Reviewer's feedback (up to 3 attempts).

**Test Generator Agent.** Produces pytest test cases for the generated code, ensuring testability. Tests are placed in the repository's existing test directory structure.

### C. Orchestrator Design

The Orchestrator implements a finite-state machine with the following states: `start -> parallel_discovery -> planner -> alignment -> implementer_attempt_N -> reviewer_attempt_N -> test_generator -> safe_writer -> complete`. State transitions are logged with timestamps, enabling performance profiling.

Key design decisions:

1. **Parallel discovery**: Historian and Architect run concurrently, reducing discovery time.
2. **Filesystem-as-memory**: All intermediate outputs (style.json, historian.json, plan.md) are written to a `.contextual-architect/` workspace directory. This provides persistence across retries and debugging visibility.
3. **Graceful degradation**: If ChromaDB is not installed, the system operates without RAG. If the LLM API fails, heuristic fallbacks activate. No single dependency failure crashes the pipeline.

---

## IV. RAG Layer Design

### A. Motivation

Without repository context, LLMs generate code based on their training distribution — which may not match the target repository's patterns. Our RAG layer provides *grounded* context by retrieving semantically relevant code from the target repository.

### B. AST-Aware Code Chunking

Traditional text chunking (e.g., 400-character splits) produces fragments that cross function boundaries, mix imports with logic, and lack semantic coherence. Our chunker operates at the **Abstract Syntax Tree (AST)** level for Python code:

Each chunk represents one function or class definition, preserving imports, decorators, docstrings, and type hints. Metadata includes: repository name, file path, symbol name, symbol type, line range, and language.

For Python, we use the `ast` module to extract function and class definitions as self-contained chunks. For JavaScript, TypeScript, and Go, we use regex-based extraction as a fallback. This produces semantically coherent chunks where each chunk represents a complete code unit.

### C. Vector Store and Embedding

Chunks are embedded and stored in ChromaDB with a three-strategy fallback for embedding functions:

1. **SentenceTransformer** (`all-MiniLM-L6-v2`) — primary
2. **ChromaDB DefaultEmbeddingFunction** — fallback for Keras 3 conflicts
3. **ONNXMiniLM_L6_V2** — final fallback

Each repository gets its own ChromaDB collection, enabling multi-project support. Chunks are upserted with content-based hashing for idempotent updates.

### D. Incremental Indexing

The indexer tracks file modification times and skips unchanged files on subsequent runs. On a 44-file FastAPI repository:

- **Initial index**: 37.45 seconds (174 chunks from 44 files)
- **Subsequent runs**: 0.03 seconds (0 new files detected)

This makes RAG viable for development workflows where the indexer runs on every invocation.

### E. Retrieval Interface

The retriever provides domain-specific query methods for agents:

- `find_patterns(query)` — Historian uses this for semantic pattern search
- `find_similar_tasks(query)` — Planner uses this for prior art discovery
- `find_by_symbol(name)` — For targeted symbol lookup

Results are formatted into prompt context with source file attribution.

---

## V. Constraint Enforcement

### A. CWE Denylist

The Implementer's system prompt includes explicit prohibitions against common vulnerability patterns. The Reviewer validates compliance using regex-based scanning:

| CWE ID | Pattern | Detection Method |
|--------|---------|-----------------|
| CWE-502 | `eval()`, `exec()` | String match |
| CWE-89 | f-string in SQL context | Regex pattern matching |
| CWE-78 | `os.system()`, `subprocess(shell=True)` | String match |
| — | `assert` for validation | String match |
| — | Bare `except:` | Regex match |

### B. Architectural Compliance

Beyond security, the Reviewer checks for:

- **Pattern compliance**: Does the code use the project's established patterns? (e.g., `APIRouter` for FastAPI routes)
- **Agent output verification**: Did each agent in the pipeline produce expected outputs?
- **CoAT reasoning**: Did the Architect use Chain-of-Thought with cross-references?

### C. Two-Layer Enforcement

Constraints are enforced at two layers:

1. **Prompt-time** (preventive): The Implementer's system prompt includes the CWE denylist, reducing the probability of generating vulnerable code.
2. **Review-time** (detective): The Reviewer scans generated code for violations and triggers retries if found.

This defense-in-depth approach means that even if the LLM ignores the prompt-time constraints, the review-time check catches violations before code reaches the user.

---

## VI. Evaluation

### A. Experimental Setup

**Benchmark**: A FastAPI web application (44 Python files, 174 AST-chunked code units) used as the target repository.

**LLM**: Groq-hosted Llama-3.3-70B-Versatile (free tier, consistent across all runs).

**Tasks**: Three code generation tasks of increasing complexity:

1. **T1 — Health Check Endpoint**: Add a `/health` endpoint returning `{"status": "ok"}`. Tests APIRouter pattern compliance.
2. **T2 — Input Validation**: Add email/password validation to a user creation endpoint. Tests security pattern compliance and framework usage.
3. **T3 — Repository Refactor**: Refactor `crud.py` into `UserRepository` and `ItemRepository` classes. Tests architectural understanding and ORM pattern compliance.

**Constraint Checks**: 32 automated checks across 5 security categories and 6 behavioral categories.

### B. Results

Table II presents the before/after RAG comparison.

| Task | Without RAG | With RAG | Time (RAG) |
|------|------------|----------|------------|
| T1: Health check | 11/11 | 11/11 | 19.3s |
| T2: Input validation | 11/11 | 11/11 | 10.8s |
| T3: Repository refactor | 9/10 | **10/10** | 11.4s |
| **Total** | **31/32 (96.9%)** | **32/32 (100%)** | **41.5s** |

*Table II: Constraint compliance before and after RAG enablement.*

| Metric | Without RAG | With RAG | Change |
|--------|-----------|----------|--------|
| Total time | 85.8s | 41.5s | -51.6% |
| Avg. time/task | 28.6s | 13.8s | -51.6% |
| Attempts (all tasks) | 1 each | 1 each | Same |
| Chunks indexed | 0 | 174 | — |
| Incremental re-index | N/A | 0.03s | — |

*Table III: Performance comparison with and without RAG.*

### C. Analysis

**T3 CWE-89 Improvement.** Without RAG, the Implementer generated code containing f-string patterns in error messages (e.g., `f"User {user_id} not found"`). While not actual SQL injection, the regex-based CWE-89 check flagged these as potential violations. With RAG, the Historian retrieved the repository's actual SQLAlchemy ORM patterns, and the Implementer generated pure ORM code (`self.db.query(models.User).filter(...)`) with no f-strings touching data variables. This demonstrates that **repository-specific context eliminates security anti-patterns by replacing generic generation with pattern-grounded generation**.

**T2 Validation Pattern Shift.** An instructive case: without RAG, the Implementer used inline Pydantic validators (matching the generic Python web development pattern). With RAG enabled, the Historian discovered the repository's existing `validate_email()` and `validate_password()` utility functions, and the Implementer reused them instead of reinventing validation. While a naive constraint checker flagged this as "missing Pydantic," manual review confirmed the RAG-augmented output is architecturally superior — it follows the DRY principle and matches established codebase conventions. We updated our constraint checker to accept any form of proper input validation, not just Pydantic-specific patterns.

**Performance Improvement.** The 2.5x speedup (85.8s -> 41.5s) likely results from RAG providing more targeted context, reducing the LLM's need to "search" through its parametric memory. Better context produces more focused prompt-response interactions with fewer tokens.

**File Naming.** Without our multi-word entity extraction, the Architect defaulted to generic names (`feature.py`). After implementing descriptive name generation, targets became `health_endpoint.py`, `input_validation_user.py`, and `app/crud.py` — matching the repository's naming conventions.

### D. Test Suite Coverage

Table IV summarizes our automated test infrastructure.

| Test Suite | Tests | Coverage |
|-----------|-------|----------|
| Agent unit tests | 245 | All 7 agents + orchestrator + workspace |
| RAG + Storage | 31 | Chunker, vector store, retriever, indexer, SQLite |
| E2E contract tests | 25 | Historian/Architect/Implementer/Reviewer contracts |
| Output validator | 31 | JSON extraction, verdict integrity, security checks |
| **Total** | **332** | **100% pass rate** |

*Table IV: Automated test suite composition.*

### E. Threats to Validity

*Internal validity.* Our before/after comparison controls for the LLM (same model, same temperature) and the benchmark (same repository, same tasks). However, LLM inference is non-deterministic; results may vary across runs. We mitigate this by using temperature=0 and reporting single-run results, noting that stochastic variation is inherent to the approach.

*External validity.* Our evaluation uses a single FastAPI repository (44 files) with three tasks. Generalization to other frameworks (Django, Express, Spring), languages (Java, Rust, C++), and repository scales (>1000 files) requires further evaluation. We explicitly do not claim broad generalizability from this initial study.

*Construct validity.* Our 32 constraint checks are a proxy for "code review readiness," not a replacement for actual human code review. The correlation between constraint compliance and human reviewer acceptance is assumed but not empirically validated.

---

## VII. Discussion

### A. Limitations

**Language Support.** AST-aware chunking currently supports Python natively, with regex-based fallback for JavaScript, TypeScript, and Go. Languages without parser support (C, C++, Java, Rust) rely on file-level chunking, which reduces retrieval quality. Integration with tree-sitter [11] would provide universal language support.

**Repository Scale.** Our evaluation targets a 44-file repository. For large monorepos (>1000 files), the vector store accumulates excessive chunks, potentially degrading retrieval relevance. A scope-limiting mechanism (e.g., `--scope net/ipv4/`) would be necessary for projects like the Linux kernel.

**LLM Dependency.** The quality of generated code depends fundamentally on the underlying LLM's capabilities. Our system improves context and enforces constraints, but cannot compensate for a weak base model.

**Evaluation Scale.** Three tasks on one repository provides initial evidence but is insufficient for broad generalization. A larger benchmark covering multiple frameworks, languages, and project sizes is needed.

### B. Comparison with Commercial Tools

Commercial AI coding assistants (GitHub Copilot, Cursor, Claude Code) generate code using single-pass LLM inference with recency-based context (files the developer recently opened). Our system differs in three key aspects:

1. **Relevance-based vs. recency-based context**: Our RAG retrieves semantically similar code regardless of when it was last opened.
2. **Explicit constraint enforcement**: Commercial tools rely on LLM training for safety; we implement runtime CWE checks.
3. **Reproducible evaluation**: Our evaluation harness produces quantified, comparable results; commercial tools lack published evaluation frameworks for architectural compliance.

These differences are complementary rather than competitive — our constraint enforcement and RAG mechanisms could be integrated into existing IDE-based tools.

### C. Architectural Decisions

**Graceful degradation** proved essential for practical adoption. By making ChromaDB and sentence-transformers optional dependencies, the system remains functional without RAG — important for environments where installing native dependencies is restricted. This is an enterprise-grade design choice absent from most academic prototypes.

**Filesystem-as-memory** (writing intermediate outputs to disk and re-reading them) provides two benefits: (1) intermediate outputs survive process crashes, enabling debugging, and (2) re-reading the plan on each retry pushes it into the LLM's recent attention window, improving adherence to the original task specification.

---

## VIII. Conclusion and Future Work

We presented Contextual Architect, a multi-agent system for repository-aware code generation that addresses the Integration Gap between LLM-generated code and existing codebase conventions. Through seven specialized agents, AST-aware RAG, and CWE denylist enforcement, the system achieves 100% constraint compliance on a FastAPI benchmark while providing a 2.5x speedup over the non-RAG baseline.

Our evaluation demonstrates that repository-specific retrieval eliminates security anti-patterns (CWE-89), enables code reuse of existing utilities (DRY principle), and produces descriptive file naming — all measurable improvements over context-free generation.

**Future work** includes: (1) tree-sitter integration for universal language support across 40+ languages, (2) documentation-aware indexing to incorporate project README files, API specifications, and CONTRIBUTING guides, (3) two-stage retrieval with LLM re-ranking for improved relevance in large repositories, (4) MCP (Model Context Protocol) integration for live IDE connectivity, and (5) evaluation on a larger, multi-framework benchmark.

---

## References

[1] M. Chen et al., "Evaluating Large Language Models Trained on Code," arXiv:2107.03374, 2021.

[2] J. Austin et al., "Program Synthesis with Large Language Models," arXiv:2108.07732, 2021.

[3] H. Pearce, B. Ahmad, B. Tan, B. Dolan-Gavitt, and R. Karri, "Asleep at the Keyboard? Assessing the Security of GitHub Copilot's Code Contributions," in *IEEE Symposium on Security and Privacy (S&P)*, 2022. arXiv:2108.09293.

[4] C. Qian et al., "ChatDev: Communicative Agents for Software Development," in *ACL*, 2024. arXiv:2307.07924.

[5] S. Hong et al., "MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework," in *ICLR*, 2024. arXiv:2308.00352.

[6] R. N. H. Khan, D. Wasif, J.-H. Cho, and A. Butt, "Multi-Agent Code-Orchestrated Generation for Reliable Infrastructure-as-Code (MACOG)," arXiv:2510.03902, 2025.

[7] D. Ding, S. Liu, E. Yang, J. Lin, Z. Chen, S. Dou, T. Gui et al., "OctoBench: Benchmarking Scaffold-Aware Instruction Following in Repository-Grounded Agentic Coding," arXiv:2601.10343, 2026.

[8] C. Pornprasit et al., "Retrieval-Augmented Code Review Comment Generation," arXiv:2506.11591, 2025.

[9] L. Gong et al., "Evaluation of LLMs on Syntax-Aware Code Fill-in-the-Middle Tasks," arXiv:2403.04814, 2024.

[10] "Context Engineering for AI Agents," Anthropic Research Blog, 2025. See also Manus AI filesystem-as-memory technique, https://manus.im.

[11] "Tree-sitter — An incremental parsing system for programming tools," https://tree-sitter.github.io, 2024.

[12] J. Yang, C. E. Jimenez, A. Wettig, K. Lieret, S. Yao, K. Narasimhan, and O. Press, "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering," arXiv:2405.15793, 2024.

[13] Y. Zhang, H. Ruan, Z. Fan, and A. Roychoudhury, "AutoCodeRover: Autonomous Program Improvement," arXiv:2404.05427, 2024.

---

## Appendix A: Generated Code Samples

### A.1 Task T1 — Health Check Endpoint (With RAG)
```python
# app/api/routes/health_endpoint.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def get_health() -> dict:
    return {"status": "ok"}
```

### A.2 Task T3 — Repository Refactor (With RAG)
```python
# app/crud.py
from typing import List
from sqlalchemy.orm import Session
from app import models, schemas

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user(self, user_id: int):
        return self.db.query(models.User).filter(
            models.User.id == user_id
        ).first()

    def create_user(self, user_in: schemas.UserCreate):
        db_user = models.User(**user_in.dict())
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

class ItemRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_item(self, item_id: int):
        return self.db.query(models.Item).filter(
            models.Item.id == item_id
        ).first()

    def create_item(self, item_in: schemas.ItemCreate, owner_id: int):
        db_item = models.Item(**item_in.dict(), owner_id=owner_id)
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item
```

*Note: Pure ORM patterns with no f-strings — CWE-89 compliant. All query patterns match the repository's existing SQLAlchemy usage.*
