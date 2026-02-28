# PROVISIONAL PATENT SPECIFICATION

## Form 2 — Indian Patent Application

---

## TITLE OF THE INVENTION

**Method and System for Multi-Agent Codebase-Aware Code Generation with Retrieval-Augmented Architectural Compliance**

*Product Name: MACRO (Multi-Agent Contextual Repository Orchestrator)*

---

## APPLICANT

**Name:** Yuvraj Sharma
**Address:** JECRC University, Jaipur, Rajasthan, India
**Nationality:** Indian

---

## FIELD OF THE INVENTION

The present invention relates to the field of automated software engineering, specifically to methods and systems for generating code that complies with existing codebase conventions, architectural patterns, and security constraints through multi-agent orchestration and retrieval-augmented generation.

---

## BACKGROUND OF THE INVENTION

Large Language Models (LLMs) are increasingly used for automated code generation. Commercial tools such as GitHub Copilot, Cursor, and Claude Code generate syntactically correct code based on natural language prompts. However, these tools suffer from a fundamental limitation referred to herein as the "Integration Gap" — the disconnect between code that compiles correctly and code that conforms to the conventions, patterns, and security requirements of the target repository.

Prior art includes:

1. **Multi-agent software development frameworks** (e.g., ChatDev, MetaGPT) that decompose code generation into role-based agents but only target new application creation ("greenfield" projects) without awareness of existing codebases.

2. **Single-agent repository-aware tools** (e.g., SWE-agent, AutoCodeRover) that operate on existing repositories but use a monolithic agent architecture without explicit security enforcement or retrieval-augmented context.

3. **Retrieval-augmented code tools** that apply RAG to code review comment generation but not to code generation itself, and that use text-based chunking rather than Abstract Syntax Tree (AST)-aware chunking.

4. **Security analysis tools** that identify vulnerabilities in LLM-generated code (approximately 40% are vulnerable per published research) but propose no runtime enforcement mechanism.

No existing system combines multi-agent orchestration, repository-grounded AST-aware retrieval, and CWE denylist enforcement in a single pipeline targeting existing codebases.

---

## SUMMARY OF THE INVENTION

The present invention provides a method and system for generating code within existing software repositories using a pipeline of specialized agents coordinated by a finite-state orchestrator, augmented by a retrieval system that provides repository-specific context through AST-aware code chunking and vector search, and validated by a constraint enforcement mechanism that implements Common Weakness Enumeration (CWE) denylist checks as a post-generation security gate.

The system achieves measurably higher compliance with repository conventions and security requirements compared to single-shot LLM generation, while reducing total generation time through improved context targeting.

---

## DETAILED DESCRIPTION OF THE INVENTION

### 1. System Overview

The invention comprises a software system that processes code generation requests through a pipeline of nine (9) specialized agents coordinated by a finite-state orchestrator, exposed via an interactive command-line interface with dual-mode operation (conversational Q&A and code generation). The agents operate on a shared context object that accumulates repository-specific information as it passes through each pipeline stage.

### 2. Agent Pipeline Architecture (Claim 1)

The pipeline consists of the following nine (9) specialized agents executed in a defined order:

**a) Historian Agent:** Performs heuristic filesystem analysis of the target repository to identify coding patterns including naming conventions (snake_case, camelCase), import patterns, error handling styles, and framework-specific idioms. When the retrieval subsystem is available, the Historian additionally performs semantic vector search to discover historically similar implementations, merging heuristic and semantic results into a unified context with confidence scores.

**b) Architect Agent:** Maps the project's directory structure, identifies reusable utilities by extracting exported functions and classes from existing files, determines necessary imports, and generates a descriptive target filename using multi-word entity extraction from the user's natural language request (e.g., "Add a health check endpoint" produces `health_endpoint.py`).

**c) Planner Agent:** Generates a structured implementation plan comprising task complexity assessment, success criteria, and step-by-step implementation instructions. The plan is persisted to disk as a file and re-read on each retry attempt, exploiting the LLM's recency bias to maintain adherence to the original task specification.

**d) Alignment Checker Agent:** Cross-validates the Planner's proposed approach against the Historian's discovered conventions and the Architect's structural analysis, catching misalignments before code generation begins.

**e) Implementer Agent:** Generates code based on accumulated context from all upstream agents. The Implementer's system prompt includes an explicit CWE denylist prohibiting known vulnerability patterns.

**f) Reviewer Agent:** Performs deterministic security scanning and structural validation using pattern matching to detect CWE violations. Issues an APPROVED or CHANGES_REQUESTED verdict. If changes are requested, the system routes back to the Implementer with the Reviewer's feedback, implementing a retry loop (maximum 3 attempts).

**g) Test Generator Agent:** Produces automated test cases for the generated code, ensuring testability and placing tests in the repository's existing test directory structure.

**h) Style Fingerprint Agent:** Extracts detailed code style patterns including naming conventions, indentation style, logging library usage, error handling patterns, and test framework preferences. These constraints are injected into the Implementer's prompt.

**i) Feedback Reader Agent:** Reads historical feedback from past generation runs, enabling the system to learn from previous successes and failures for the same repository.

**Key novelty:** The parallel execution of discovery agents (Historian, Architect, and Style Fingerprint) combined with the sequential execution of planning, generation, and validation agents creates a pipeline that balances information gathering efficiency with generation quality control. No prior system implements this specific combination of parallel discovery with sequential generation and validation for existing repositories.

### 3. AST-Aware Code Chunking for Retrieval-Augmented Generation (Claim 2)

The invention includes a method for indexing software repositories at the Abstract Syntax Tree level:

**a)** For Python source files, the system uses the `ast` module to parse source code and extract function definitions and class definitions as self-contained chunks. Each chunk preserves the complete code unit including imports, decorators, docstrings, and type annotations.

**b)** For JavaScript, TypeScript, and Go source files, the system uses regex-based extraction patterns as a fallback mechanism.

**c)** Each extracted chunk is stored with rich metadata comprising: repository name, file path, symbol name, symbol type (function/class/method), line range (start and end), and programming language.

**d)** Chunks are embedded into vector representations using a three-strategy fallback: (i) SentenceTransformer model (all-MiniLM-L6-v2) as primary, (ii) ChromaDB DefaultEmbeddingFunction as secondary, (iii) ONNXMiniLM_L6_V2 as tertiary. This fallback chain ensures the embedding subsystem operates regardless of dependency availability.

**e)** Embedded chunks are stored in a ChromaDB vector database with content-based hashing for idempotent upserts. Each repository receives its own collection, enabling multi-project support.

**Key novelty:** No existing code generation system chunks code at AST boundaries (function/class definitions) for semantic retrieval. Prior systems use either text-based chunking (which produces fragments crossing function boundaries) or AST-based navigation (which does not produce searchable vector representations).

### 4. Dual-Signal Repository Context Discovery (Claim 3)

The Historian Agent employs two complementary signals for discovering repository conventions:

**a) Heuristic signal:** Filesystem traversal with pattern matching to identify naming conventions, import styles, error handling patterns, and framework-specific idioms through direct file analysis.

**b) Semantic signal:** Vector search against the AST-chunked repository index to discover semantically similar implementations based on the user's request.

**c) Merge strategy:** Results from both signals are merged with confidence scores into a unified context representation that is passed to downstream agents.

**Key novelty:** No existing system combines heuristic filesystem analysis with semantic vector search and merges results with confidence scores for code generation context.

### 5. CWE Denylist Enforcement with Two-Layer Validation (Claim 4)

The invention implements a defense-in-depth approach to security constraint enforcement:

**a) Preventive layer (prompt-time):** The Implementer Agent's system prompt includes explicit prohibitions against specific CWE categories:
- CWE-502: Prohibition of `eval()` and `exec()` on untrusted input
- CWE-89: Prohibition of f-string SQL queries; requirement for parameterized queries or ORM
- CWE-78: Prohibition of `os.system()` and `subprocess(shell=True)`
- Prohibition of `assert` statements for input validation
- Prohibition of bare `except:` clauses

**b) Detective layer (review-time):** The Reviewer Agent scans generated code using regex-based pattern matching against the CWE denylist. Violations trigger an automated retry loop where the Implementer regenerates code with the Reviewer's feedback.

**Key novelty:** No existing code generation system implements a two-layer (preventive + detective) CWE enforcement mechanism with automated retry. Prior systems either rely solely on the LLM's training-time behavior (no enforcement) or use domain-specific policy engines (e.g., OPA for Infrastructure-as-Code) that are not applicable to general-purpose code.

### 6. Plan Anchoring via Filesystem-as-Memory (Claim 5)

The invention employs a technique for improving LLM adherence to task specifications:

**a)** The Planner Agent writes its implementation plan to persistent storage as a file within a workspace directory.

**b)** On each retry attempt (triggered by Reviewer rejection), the plan file is re-read from disk and included in the Implementer's prompt context.

**c)** This exploits the documented "lost in the middle" phenomenon in LLMs, where models disproportionately attend to content at the beginning and end of their context window. By re-reading the plan, it is placed in the LLM's recent attention window, reducing drift from the original task specification.

**d)** All intermediate agent outputs (style analysis, architecture analysis, plan) are persisted to disk, providing crash recovery and debugging visibility.

**Key novelty:** The deliberate exploitation of LLM attention patterns through filesystem-based re-reading of intermediate outputs to improve generation consistency across retry attempts.

### 7. Incremental Indexing (Claim 6)

The retrieval subsystem tracks file modification timestamps and skips unchanged files on subsequent indexing runs:

**a)** On initial indexing, all source files in the repository are parsed, chunked, embedded, and stored.

**b)** On subsequent runs, only files with modified timestamps are re-processed.

**c)** This reduces indexing time from 37.45 seconds (initial) to 0.03 seconds (subsequent) on a 44-file repository, making the retrieval subsystem viable for use on every code generation invocation.

**Key novelty:** Incremental AST-aware indexing that enables sub-second re-indexing for development workflows.

### 8. Graceful Degradation (Claim 7)

The system operates at full capability when all dependencies are available, but degrades gracefully when optional components are absent:

**a)** If ChromaDB is not installed, the system operates without retrieval augmentation, using only heuristic context.

**b)** If the sentence-transformers library is not available, the system falls back to alternative embedding strategies.

**c)** If the LLM API fails, heuristic fallback values are used for agent outputs.

**d)** No single dependency failure causes the pipeline to crash or become unavailable.

**Key novelty:** Enterprise-grade graceful degradation in an academic prototype, where RAG, embeddings, and LLM connectivity are all independently optional.

---

## CLAIMS

**1.** A method for generating code within an existing software repository, comprising:
- (a) receiving a natural language code generation request;
- (b) scanning the repository using a Historian Agent to discover coding patterns, naming conventions, and framework-specific idioms through heuristic filesystem analysis;
- (c) mapping the repository structure using an Architect Agent to identify reusable utilities, exported functions, and appropriate file placement for generated code;
- (d) executing steps (b) and (c) in parallel to reduce discovery time;
- (e) generating a structured implementation plan using a Planner Agent informed by the context from steps (b) and (c);
- (f) cross-validating the plan against discovered conventions using an Alignment Checker Agent;
- (g) generating code using an Implementer Agent whose prompt includes a CWE denylist;
- (h) validating generated code using a Reviewer Agent that performs deterministic security scanning;
- (i) if the Reviewer rejects the code, routing back to step (g) with feedback (up to a maximum number of retry attempts);
- (j) generating automated test cases using a Test Generator Agent; and
- (k) writing the generated code and tests to the repository using a Safe Writer.

**2.** A method for indexing a software repository for retrieval-augmented code generation, comprising:
- (a) parsing source code files using an Abstract Syntax Tree parser to identify function definitions and class definitions;
- (b) extracting each function and class definition as a self-contained chunk preserving imports, decorators, docstrings, and type annotations;
- (c) associating each chunk with metadata including repository name, file path, symbol name, symbol type, line range, and programming language;
- (d) embedding chunks into vector representations using a fallback chain of embedding functions; and
- (e) storing embedded chunks in a vector database with content-based hashing for idempotent updates.

**3.** A method for discovering repository coding conventions using dual-signal analysis, comprising:
- (a) performing heuristic filesystem analysis to identify coding patterns;
- (b) performing semantic vector search against an AST-chunked index to find similar implementations;
- (c) merging results from steps (a) and (b) with confidence scores into a unified context representation.

**4.** A method for enforcing security constraints on LLM-generated code, comprising:
- (a) including explicit CWE-category prohibitions in the code generation prompt (preventive layer);
- (b) scanning generated code using pattern matching against a CWE denylist (detective layer);
- (c) upon detection of a violation in step (b), routing the code back to the generation step with the reviewer's feedback and repeating until the code is compliant or a maximum number of attempts is reached.

**5.** A method for improving LLM adherence to task specifications in iterative code generation, comprising:
- (a) generating an implementation plan and persisting it to filesystem storage;
- (b) on each subsequent generation attempt, re-reading the persisted plan from the filesystem;
- (c) including the re-read plan in the LLM's prompt context, thereby placing it in the model's recent attention window and reducing specification drift across retry attempts.

**6.** A method for incremental indexing of a software repository for retrieval-augmented code generation, comprising:
- (a) tracking file modification timestamps during initial repository indexing;
- (b) on subsequent indexing runs, comparing current file modification timestamps against stored timestamps;
- (c) re-processing only files whose timestamps have changed; and
- (d) skipping unchanged files to achieve sub-second re-indexing time.

**7.** A system for code generation within existing software repositories that degrades gracefully when optional components are unavailable, comprising:
- (a) a multi-agent pipeline of nine (9) specialized agents that operates with or without a vector database for retrieval augmentation;
- (b) an embedding subsystem with a multi-strategy fallback chain;
- (c) a pipeline that continues execution using heuristic fallback values when the LLM API is unavailable;
- wherein no single optional component failure prevents the system from producing a code generation result.

**8.** A method for interactive code generation providing dual-mode operation, comprising:
- (a) receiving user input through a command-line interface;
- (b) classifying user intent as either "chat" (informational query) or "build" (code generation request) using keyword-based and pattern-based detection;
- (c) for chat intents, collecting relevant file contents from the repository using safe path resolution that prevents directory traversal attacks, and generating a response using an LLM with prompt injection guards;
- (d) for build intents, executing the full multi-agent pipeline of Claim 1;
- (e) if the user's input contains pseudocode delimited by a separator token, verifying that the generated code implements each pseudocode step through keyword mapping and pattern analysis.

**9.** A method for hardening an LLM-based code generation system against security threats, comprising:
- (a) resolving all user-provided file path references against the repository root directory and rejecting any resolved path that falls outside the repository boundary (preventing path traversal attacks);
- (b) masking API credentials before persisting configuration to storage, retaining only the first and last four characters of each key;
- (c) enforcing a maximum input length to prevent resource exhaustion;
- (d) including explicit prompt injection detection instructions in the LLM system prompt, instructing the model to ignore adversarial instructions embedded in user-provided code files;
- (e) automatically creating filesystem-level exclusion rules in the workspace directory to prevent accidental disclosure of intermediate outputs.

---

## ABSTRACT

A method and system (MACRO — Multi-Agent Contextual Repository Orchestrator) for generating code within existing software repositories using a pipeline of nine specialized agents coordinated by a finite-state orchestrator, accessible through a dual-mode interactive CLI supporting both conversational Q&A and pipelined code generation. The system addresses the "Integration Gap" between LLM-generated code and existing codebase conventions through four mechanisms: (1) a nine-agent pipeline (Historian, Architect, Style Fingerprint, Planner, Alignment Checker, Implementer, Reviewer, Test Generator, Feedback Reader) with parallel discovery and sequential generation; (2) a retrieval-augmented generation layer that indexes repositories using Abstract Syntax Tree-aware code chunking at function and class boundaries, stored in a vector database with incremental indexing; (3) a two-layer CWE denylist enforcement mechanism combining prompt-time prevention with review-time detection and automated retry; and (4) a security hardening layer providing path traversal prevention, API credential masking, input length enforcement, and prompt injection guards. Evaluation on a FastAPI benchmark demonstrates 96.9% constraint compliance (31/32 checks) without RAG and 100% (32/32) with RAG enabled, and a 51.6% reduction in total generation time.

---

## DRAWINGS

*Drawing 1: System Architecture (corresponds to Fig. 1 in associated publication)*
— [To be prepared as a formal patent drawing from the pipeline diagram]

*Drawing 2: AST-Aware Chunking Process*
— [To be prepared showing: Source File → AST Parser → Function/Class Extraction → Metadata Enrichment → Vector Embedding → ChromaDB Storage]

*Drawing 3: Two-Layer CWE Enforcement Flow*
— [To be prepared showing: Prompt-time Denylist → Code Generation → Review-time Scanning → APPROVED/CHANGES_REQUESTED decision with retry loop]

---

## DATE

Filed: [DATE TO BE FILLED]

## SIGNATURE

[APPLICANT SIGNATURE]
