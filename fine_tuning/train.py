"""
QLoRA Fine-Tuning Script for MACRO Distillation.

Uses Unsloth + PEFT to fine-tune Qwen2.5-Coder-7B on MACRO trace data.
This creates a specialized model that understands the inter-agent
communication protocol and produces plans/code in MACRO's format.

Requirements:
    - GPU with 24GB+ VRAM (A100 40GB recommended)
    - Python 3.10+
    - pip install -r requirements-gpu.txt

Usage:
    python train.py --dataset data/train.jsonl --epochs 3

Full options:
    python train.py \\
        --base-model "Qwen/Qwen2.5-Coder-7B-Instruct" \\
        --dataset data/train.jsonl \\
        --output-dir output/macro-planner-v1 \\
        --epochs 3 \\
        --batch-size 4 \\
        --lora-rank 64 \\
        --lr 2e-4
"""

import argparse
import json
import os
import sys
from pathlib import Path


def check_gpu():
    """Verify GPU is available."""
    try:
        import torch
        if not torch.cuda.is_available():
            print("  [X] No CUDA GPU detected!")
            print("      This script requires a GPU. Options:")
            print("      - RunPod: runpod.io (A100 ~$1.64/hr)")
            print("      - Google Colab Pro: colab.google ($10/mo)")
            print("      - Lambda Labs: lambdalabs.com")
            sys.exit(1)
        
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_mem / 1024**3
        print(f"  GPU: {gpu_name} ({gpu_mem:.0f}GB)")
        return True
    except ImportError:
        print("  [X] PyTorch not installed. Run: pip install -r requirements-gpu.txt")
        sys.exit(1)


def load_dataset(path: str):
    """Load training data from JSONL."""
    examples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune a model for MACRO using QLoRA"
    )
    parser.add_argument(
        "--base-model",
        default="Qwen/Qwen2.5-Coder-7B-Instruct",
        help="Base model from HuggingFace (default: Qwen2.5-Coder-7B)",
    )
    parser.add_argument(
        "--dataset",
        default="data/train.jsonl",
        help="Training data JSONL file",
    )
    parser.add_argument(
        "--output-dir",
        default="output/macro-planner-v1",
        help="Output directory for fine-tuned model",
    )
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=4, help="Batch size per GPU")
    parser.add_argument("--grad-accum", type=int, default=4, help="Gradient accumulation steps")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--lora-rank", type=int, default=64, help="LoRA rank (higher = more capacity)")
    parser.add_argument("--lora-alpha", type=int, default=16, help="LoRA alpha")
    parser.add_argument("--max-seq-len", type=int, default=4096, help="Max sequence length")
    parser.add_argument("--warmup-steps", type=int, default=10, help="Warmup steps")
    
    args = parser.parse_args()
    
    print()
    print("  MACRO QLoRA Fine-Tuning")
    print("  " + "=" * 40)
    
    # Check GPU
    check_gpu()
    
    # Check dataset
    if not Path(args.dataset).exists():
        print(f"  [X] Dataset not found: {args.dataset}")
        print(f"      Run these first:")
        print(f"      1. python generate_training_data.py")
        print(f"      2. python format_dataset.py")
        sys.exit(1)
    
    # Load dataset
    examples = load_dataset(args.dataset)
    print(f"  Dataset: {len(examples)} examples")
    print(f"  Model:   {args.base_model}")
    print(f"  Epochs:  {args.epochs}")
    print(f"  LoRA:    rank={args.lora_rank}, alpha={args.lora_alpha}")
    print(f"  LR:      {args.lr}")
    print(f"  Output:  {args.output_dir}")
    print()
    
    # ── Load model with Unsloth (4-bit quantization) ──────────
    print("  Loading model with 4-bit quantization...")
    
    try:
        from unsloth import FastLanguageModel
    except ImportError:
        print("  [X] Unsloth not installed.")
        print("      Run: pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'")
        print("      Or:  pip install -r requirements-gpu.txt")
        sys.exit(1)
    
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_len,
        dtype=None,  # Auto-detect (float16 on most GPUs)
        load_in_4bit=True,  # QLoRA: 4-bit base model
    )
    
    print(f"  Model loaded: {args.base_model}")
    
    # ── Add LoRA adapters ─────────────────────────────────────
    print("  Adding LoRA adapters...")
    
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_rank,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=args.lora_alpha,
        lora_dropout=0,  # Unsloth recommends 0 for efficiency
        bias="none",
        use_gradient_checkpointing="unsloth",  # 60% less VRAM
        random_state=42,
    )
    
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"  Trainable: {trainable:,} / {total:,} params ({100*trainable/total:.2f}%)")
    
    # ── Format dataset for training ───────────────────────────
    print("  Formatting dataset...")
    
    from datasets import Dataset
    
    def format_chat(example):
        """Convert ChatML messages to tokenized format."""
        text = tokenizer.apply_chat_template(
            example["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
        return {"text": text}
    
    dataset = Dataset.from_list(examples)
    dataset = dataset.map(format_chat, remove_columns=dataset.column_names)
    
    print(f"  Formatted {len(dataset)} examples")
    
    # Show a sample
    print(f"  Sample (first 200 chars): {dataset[0]['text'][:200]}...")
    print()
    
    # ── Training ──────────────────────────────────────────────
    print("  Starting training...")
    
    from trl import SFTTrainer
    from transformers import TrainingArguments
    
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=args.warmup_steps,
        weight_decay=0.01,
        fp16=True,
        logging_steps=5,
        save_steps=50,
        save_total_limit=3,
        optim="adamw_8bit",
        seed=42,
        report_to="none",  # Disable wandb unless configured
    )
    
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
        dataset_text_field="text",
        max_seq_length=args.max_seq_len,
        packing=True,  # Pack multiple examples per sequence
    )
    
    # Train
    stats = trainer.train()
    
    print()
    print("  " + "=" * 40)
    print(f"  Training complete!")
    print(f"  Loss:    {stats.training_loss:.4f}")
    print(f"  Runtime: {stats.metrics['train_runtime']:.0f}s")
    print(f"  Samples: {stats.metrics['train_samples_per_second']:.1f}/s")
    
    # ── Save ──────────────────────────────────────────────────
    print(f"\n  Saving model to {output_dir}...")
    
    # Save LoRA adapter
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    
    # Also save merged model (for GGUF export)
    merged_dir = output_dir + "-merged"
    print(f"  Saving merged model to {merged_dir}...")
    model.save_pretrained_merged(merged_dir, tokenizer, save_method="merged_16bit")
    
    print()
    print("  " + "=" * 40)
    print(f"  Done! Model saved to:")
    print(f"    LoRA adapter: {output_dir}")
    print(f"    Merged model: {merged_dir}")
    print(f"\n  Next steps:")
    print(f"    python export_gguf.py --model-dir {merged_dir}")
    print()


if __name__ == "__main__":
    main()
