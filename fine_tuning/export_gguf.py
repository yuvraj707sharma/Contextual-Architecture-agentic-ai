"""
Export fine-tuned MACRO model to GGUF format for Ollama.

Converts the HuggingFace model to GGUF with quantization,
making it runnable via `ollama run macro-planner`.

Requirements:
    pip install llama-cpp-python

Usage:
    python export_gguf.py --model-dir output/macro-planner-v1-merged
    python export_gguf.py --model-dir output/macro-planner-v1-merged --quant Q4_K_M
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def check_llama_cpp():
    """Check if llama.cpp conversion tools are available."""
    # Try to find convert script
    try:
        import llama_cpp
        return True
    except ImportError:
        return False


def export_with_unsloth(model_dir: str, output_path: str, quant: str):
    """Export using Unsloth's built-in GGUF export (recommended)."""
    print("  Using Unsloth GGUF export...")
    
    try:
        from unsloth import FastLanguageModel
    except ImportError:
        print("  [X] Unsloth not installed.")
        print("      Run: pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'")
        sys.exit(1)
    
    # Load the merged model
    print(f"  Loading model from {model_dir}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_dir,
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=False,  # Load in full precision for export
    )
    
    # Export to GGUF
    print(f"  Exporting to GGUF with {quant} quantization...")
    
    # Unsloth supports direct GGUF save
    output_dir = str(Path(output_path).parent)
    model.save_pretrained_gguf(
        output_dir,
        tokenizer,
        quantization_method=quant,
    )
    
    # Find the generated GGUF file
    gguf_files = list(Path(output_dir).glob("*.gguf"))
    if gguf_files:
        # Rename to our desired output path
        generated = gguf_files[0]
        final_path = Path(output_path)
        if generated != final_path:
            generated.rename(final_path)
        print(f"  Exported: {final_path}")
        print(f"  Size: {final_path.stat().st_size / 1024**3:.1f}GB")
        return str(final_path)
    
    print("  [X] GGUF file not found after export")
    return None


def export_with_llama_cpp(model_dir: str, output_path: str, quant: str):
    """Export using llama.cpp convert script (fallback)."""
    print("  Using llama.cpp conversion (fallback)...")
    
    # Step 1: Convert HF model to GGUF (FP16)
    fp16_path = output_path.replace(f".{quant}.", ".fp16.")
    
    convert_script = "convert_hf_to_gguf.py"
    
    # Try to find llama.cpp
    llama_cpp_path = os.environ.get("LLAMA_CPP_PATH", "")
    if llama_cpp_path:
        convert_script = os.path.join(llama_cpp_path, convert_script)
    
    print(f"  Step 1: Converting to FP16 GGUF...")
    result = subprocess.run(
        [sys.executable, convert_script, model_dir, "--outfile", fp16_path, "--outtype", "f16"],
        capture_output=True, text=True,
    )
    
    if result.returncode != 0:
        print(f"  [X] Conversion failed: {result.stderr}")
        print(f"      Make sure llama.cpp is installed:")
        print(f"      git clone https://github.com/ggerganov/llama.cpp")
        print(f"      export LLAMA_CPP_PATH=/path/to/llama.cpp")
        return None
    
    # Step 2: Quantize
    print(f"  Step 2: Quantizing to {quant}...")
    quantize_bin = "llama-quantize"
    if llama_cpp_path:
        quantize_bin = os.path.join(llama_cpp_path, "build", "bin", quantize_bin)
    
    result = subprocess.run(
        [quantize_bin, fp16_path, output_path, quant],
        capture_output=True, text=True,
    )
    
    if result.returncode != 0:
        print(f"  [X] Quantization failed: {result.stderr}")
        return None
    
    # Clean up FP16 file
    if os.path.exists(fp16_path):
        os.remove(fp16_path)
    
    print(f"  Exported: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Export fine-tuned model to GGUF for Ollama"
    )
    parser.add_argument(
        "--model-dir",
        required=True,
        help="Path to merged HuggingFace model directory",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output GGUF path (default: auto-generated)",
    )
    parser.add_argument(
        "--quant",
        default="Q4_K_M",
        choices=["Q4_K_M", "Q5_K_M", "Q8_0", "f16"],
        help="Quantization level (default: Q4_K_M, ~4.5GB for 7B model)",
    )
    
    args = parser.parse_args()
    
    if not Path(args.model_dir).exists():
        print(f"  [X] Model directory not found: {args.model_dir}")
        sys.exit(1)
    
    # Auto-generate output path
    if args.output is None:
        model_name = Path(args.model_dir).name.replace("-merged", "")
        args.output = f"output/{model_name}.{args.quant}.gguf"
    
    os.makedirs(Path(args.output).parent, exist_ok=True)
    
    print()
    print("  MACRO GGUF Export")
    print("  " + "=" * 40)
    print(f"  Model: {args.model_dir}")
    print(f"  Quant: {args.quant}")
    print(f"  Output: {args.output}")
    print()
    
    # Try Unsloth first (easier), then llama.cpp (manual)
    try:
        result = export_with_unsloth(args.model_dir, args.output, args.quant)
    except Exception as e:
        print(f"  Unsloth export failed: {e}")
        print(f"  Trying llama.cpp fallback...")
        result = export_with_llama_cpp(args.model_dir, args.output, args.quant)
    
    if result:
        print()
        print("  " + "=" * 40)
        print(f"  Export complete!")
        print(f"\n  Next steps:")
        print(f"    1. Copy {result} to your machine")
        print(f"    2. ollama create macro-planner -f Modelfile")
        print(f"    3. macro -i --provider ollama --model macro-planner")
    else:
        print("\n  [X] Export failed. See errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
