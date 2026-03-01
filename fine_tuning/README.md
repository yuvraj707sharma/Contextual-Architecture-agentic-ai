# MACRO Fine-Tuning Pipeline

## Overview

This pipeline fine-tunes a small reasoning model (Qwen2.5-Coder-7B) to serve
as MACRO's Planner + Thinker agent. The model learns YOUR pipeline's inter-agent
communication protocol, not general coding ability.

## Prerequisites

- **GPU**: RunPod A100 40GB (~$1.64/hr) or Google Colab Pro ($10/mo)
- **Time**: ~2-4 hours for 500 examples on A100
- **Cost**: ~$5-10 total

## Step-by-Step Guide

### Step 1: Generate Training Data (run on YOUR machine)

```bash
cd fine_tuning
pip install -r requirements.txt

# Generate synthetic training data by running MACRO with Gemini on sample tasks
python generate_training_data.py --provider google --num-tasks 50

# This creates: data/raw_traces.jsonl
```

### Step 2: Format Dataset

```bash
# Convert raw traces to training format (instruction/input/output)
python format_dataset.py --input data/raw_traces.jsonl --output data/train.jsonl

# This creates: data/train.jsonl (ChatML format for Qwen)
```

### Step 3: Upload Data to Cloud GPU

```bash
# Option A: RunPod
# 1. Go to runpod.io, rent an A100 40GB ($1.64/hr)
# 2. Select "RunPod Pytorch 2.1" template
# 3. Upload data/train.jsonl to /workspace/

# Option B: Google Colab Pro
# 1. Upload train.py and data/train.jsonl to Google Drive
# 2. Open train.py as a Colab notebook
```

### Step 4: Fine-Tune (on cloud GPU)

```bash
pip install -r requirements-gpu.txt

# Train with QLoRA (4-bit quantization)
python train.py \
    --base-model "Qwen/Qwen2.5-Coder-7B-Instruct" \
    --dataset data/train.jsonl \
    --output-dir output/macro-planner-v1 \
    --epochs 3 \
    --batch-size 4 \
    --lora-rank 64
```

### Step 5: Export to GGUF (for Ollama)

```bash
python export_gguf.py \
    --model-dir output/macro-planner-v1 \
    --output output/macro-planner-v1.Q4_K_M.gguf \
    --quant Q4_K_M
```

### Step 6: Test with Ollama (on your machine)

```bash
# Copy the GGUF file to your machine, then:
ollama create macro-planner -f Modelfile
ollama run macro-planner "Plan: Add JWT auth"

# Use with MACRO:
macro -i --provider ollama --model macro-planner
```

## File Structure

```
fine_tuning/
├── README.md                    # This file
├── requirements.txt             # Local deps (data generation)
├── requirements-gpu.txt         # GPU deps (training)
├── generate_training_data.py    # Step 1: create synthetic data
├── format_dataset.py            # Step 2: format for training
├── train.py                     # Step 3: QLoRA fine-tuning
├── export_gguf.py               # Step 4: convert to GGUF
├── Modelfile                    # Step 5: Ollama model definition
├── sample_tasks.py              # Sample coding tasks for data gen
└── data/                        # Generated data (gitignored)
    ├── raw_traces.jsonl
    └── train.jsonl
```
