
1

Automatic Zoom
SimpleMem: Efficient Lifelong Memory for LLM Agents
Jiaqi Liu 1 * Yaofeng Su 1 * Peng Xia 1 Siwei Han 1
Zeyu Zheng 2 Cihang Xie 3 Mingyu Ding 1 Huaxiu Yao 1
Abstract
To support long-term interaction in complex envi-
ronments, LLM agents require memory systems
that manage historical experiences. Existing ap-
proaches either retain full interaction histories via
passive context extension, leading to substantial
redundancy, or rely on iterative reasoning to filter
noise, incurring high token costs. To address this
challenge, we introduce SimpleMem, an efficient
memory framework based on semantic lossless
compression. We propose a three-stage pipeline
designed to maximize information density and
token utilization: (1) Semantic Structured Com-
pression, which distills unstructured interactions
into compact, multi-view indexed memory units;
(2) Online Semantic Synthesis, an intra-session
process that instantly integrates related context
into unified abstract representations to eliminate
redundancy; and (3) Intent-Aware Retrieval Plan-
ning, which infers search intent to dynamically
determine retrieval scope and construct precise
context efficiently. Experiments on benchmark
datasets show that our method consistently outper-
forms baseline approaches in accuracy, retrieval
efficiency, and inference cost, achieving an aver-
age F1 improvement of 26.4% in LoCoMo while
reducing inference-time token consumption by up
to 30×, demonstrating a superior balance between
performance and efficiency. Code is available at
https://github.com/aiming-lab/SimpleMem.
1. Introduction
Large Language Model (LLM) agents have recently demon-
strated remarkable capabilities across a wide range of
tasks (Xia et al., 2025; Team et al., 2025; Qiu et al., 2025).
However, constrained by fixed context windows, existing
*Equal contribution 1UNC-Chapel Hill 2University of Cal-
ifornia, Berkeley 3University of California, Santa Cruz. Cor-
respondence to: Jiaqi Liu <jqliu@cs.unc.edu>, Mingyu Ding
<md@cs.unc.edu>, Huaxiu Yao <huaxiu@cs.unc.edu>.
Preprint. January 30, 2026.
agents exhibit significant limitations when engaging in long-
context and multi-turn interaction scenarios (Liu et al., 2023;
Wang et al., 2024a; Liu et al., 2025; Hu et al., 2025; Tu
et al., 2025). To facilitate reliable long-term interaction,
LLM agents require robust memory systems to efficiently
manage and utilize historical experience (Dev & Taranjeet,
2024; Fang et al., 2025; Wang & Chen, 2025; Tang et al.,
2025; Yang et al., 2025; Ouyang et al., 2025).
While recent research has extensively explored the design
of memory modules for LLM agents, current systems still
suffer from suboptimal retrieval efficiency and low token
utilization (Fang et al., 2025; Hu et al., 2025). On one hand,
many existing systems maintain complete interaction histo-
ries through full-context extension (Li et al., 2025; Zhong
et al., 2024). However, this approach introduce substantial
redundant information (Hu et al., 2025). Specifically, during
long-horizon interactions, user inputs and model responses
accumulate substantial low-entropy noise (e.g., repetitive
logs, non-task-oriented dialogue), which degrades the effec-
tive information density of the memory buffer. This redun-
dancy adversely affects memory retrieval and downstream
reasoning, often leading to middle-context degradation phe-
nomena (Liu et al., 2023), while also incurring significant
computational overhead during retrieval and secondary infer-
ence. On the other hand, some agentic frameworks mitigate
noise through online filtering based on iterative reasoning
procedures (Yan et al., 2025; Packer et al., 2023). Although
such approaches improve retrieval relevance, they rely on
repeated inference cycles, resulting in substantial compu-
tational cost, including increased latency and token usage.
As a result, neither paradigm achieves efficient allocation of
memory and computation resources.
To address these limitations, we introduce SimpleMem, an
efficient memory framework inspired by the Complemen-
tary Learning Systems (CLS) theory (Kumaran et al., 2016)
and built around structured semantic compression. The ob-
jective of SimpleMem is to improve information efficiency
under fixed context and token budgets. We develop a three-
stage pipeline that supports dynamic memory compression,
organization, and adaptive retrieval: (1) Semantic Struc-
tured Compression: we apply a semantic density gating
mechanism via LLM-based qualitative assessment. The
system uses the foundation model as a semantic judge to
1
arXiv:2601.02553v3 [cs.AI] 29 Jan 2026
SimpleMem: Efficient Lifelong Memory for LLM AgentsLoCoMo(Full)
ReadAgent
MemoryBank
MemGPT
A-Mem
LightMem
Mem0
SimpleMem (Ours)
Average Token Cost (Log Scale)
Performance(F1 Score)
10! 10"
10
20
30
40
50 SimpleMem (Ours)
Figure 1. Performance vs. Efficiency Trade-off. Comparison of
F1 against Token Cost on the LoCoMo benchmark. SimpleMem
achieves high accuracy with minimal token consumption.
estimate information gain relative to history, preserving only
content with high downstream utility. Retained information
is reformulated into compact memory units and indexed
jointly using dense semantic embeddings, sparse lexical fea-
tures, and symbolic metadata. (2) Online Semantic Synthe-
sis: inspired by biological consolidation and optimized for
real-time interaction, we introduce an intra-session process
that reorganizes memory on-the-fly. Related memory units
are synthesized into higher-level abstract representations
during the write phase, allowing repetitive or structurally
similar experiences to be denoised and compressed imme-
diately. (3) Intent-Aware Retrieval Planning: we employ
a planning-based retrieval strategy that infers latent search
intent to determine retrieval scope dynamically. The system
constructs a precise context by querying multiple indexes
(symbolic, semantic, lexical) and unifying results through
ID-based deduplication, balancing structural constraints and
semantic relevance without complex linear weighting.
Our primary contribution is SimpleMem, an efficient mem-
ory framework grounded in structured semantic compres-
sion, which improves information efficiency through prin-
cipled memory organization, online synthesis, and intent-
aware planning. As shown in Figure 1, our empirical ex-
periments demonstrate that SimpleMem establishes a new
state-of-the-art with an F1 score, outperforming strong base-
lines like Mem0 by 26.4%, while reducing inference token
consumption by 30× compared to full-context models.
2. The SimpleMem Architecture
In this section, we present SimpleMem, which operates
through a three-stage pipeline (see Figure 2 for the detailed
architecture). Specifically, we first describe the Semantic
Structured Compression, which utilizes implicit semantic
gating to filter redundant interaction content and reformulate
raw dialogue streams into compact memory units. Next, we
describe Online Semantic Synthesis, an on-the-fly mecha-
nism that instantly synthesizes related memory units into
higher-level abstract representations, ensuring a compact
and noise-free memory topology. Finally, we present Intent-
Aware Retrieval Planning, which infers latent search intent
to dynamically adjust retrieval scope, constructing precise
and token-efficient contexts for downstream reasoning.
2.1. Semantic Structured Compression
A primary bottleneck in long-term interaction is context
inflation, the accumulation of raw, low-entropy dialogue.
For example, a large portion of interaction segments in the
real-world consists of phatic chit-chat or redundant confir-
mations, which contribute little to downstream reasoning
but consume substantial context capacity. To address this,
we introduce a mechanism to actively filter and restructure
information at the source.
Specifically, first, incoming dialogue is segmented into over-
lapping sliding windows W of fixed length, where each
window represents a short contiguous span of recent interac-
tion. These windows serve as the basic units for processing.
Unlike traditional approaches that rely on rigid heuristic
filters or separate classification models, we employ an im-
plicit semantic density gating mechanism integrated directly
into the generation process. We model the information as-
sessment as an instruction-following task performed by the
foundation model itself. The system leverages the attention
mechanism of the LLM f to identify high-entropy spans
within the window W relative to the immediate history H.
Formally, we define the gating function Φgate not as a binary
classifier, but as a generative filter resulting from the model’s
extraction capability:
Φgate(W ) → {mk} s.t. |{mk}| ≥ 0 (1)
Here, the generation of an empty set (∅) inherently signifies
a low-density window (e.g., pure phatic chitchat), effec-
tively discarding it without explicit threshold tuning. This
instruction-driven gating allows the system to capture sub-
tle semantic nuances while naturally filtering redundancy
through the model’s semantic compression objectives.
For windows containing valid semantic content, the sys-
tem performs a unified De-linearization Transformation
Fθ . Instead of sequential independent modules, we opti-
mize the extraction, coreference resolution, and temporal
anchoring as a joint generation task. The transformation
projects the raw dialogue window W directly into a set of
context-independent memory units {mk}:
{mk} = Fθ (W ; H) ≈ (gtime ◦ gcoref ◦ gext)(W ). (2)
In this unified pass, the model follows strict instructional
constraints to: (1) resolve ambiguous pronouns to specific
entity names (gcoref), (2) convert relative temporal expres-
sions into absolute ISO-8601 timestamps (gtime), and (3)
atomize complex dialogue flows into self-contained factual
statements. By aggregating all resulting units mk across
sliding windows, we obtain the complete memory set M.
2
