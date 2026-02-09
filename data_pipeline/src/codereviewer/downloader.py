"""
CodeReviewer Dataset Downloader & Converter.

Downloads the Microsoft CodeReviewer dataset from Zenodo and converts it
to our JSONL training format for the Contextual Architect project.

Dataset: https://zenodo.org/record/6900648
Paper: https://arxiv.org/abs/2203.09095
"""

import json
import os
import zipfile
from pathlib import Path
from typing import Iterator, Dict, Any
import requests
from tqdm import tqdm


# CodeReviewer dataset URLs (from Zenodo)
DATASET_URLS = {
    "code_refinement": "https://zenodo.org/record/6900648/files/code_refinement.zip",
    "code_review": "https://zenodo.org/record/6900648/files/code_review.zip",
}

# Languages we care about
TARGET_LANGUAGES = {"go", "python", "javascript", "typescript"}


def download_file(url: str, output_path: Path) -> None:
    """Download a file with progress bar."""
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(output_path, 'wb') as f:
        with tqdm(total=total_size, unit='B', unit_scale=True, desc=output_path.name) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                pbar.update(len(chunk))


def extract_zip(zip_path: Path, extract_to: Path) -> None:
    """Extract a zip file."""
    print(f"📦 Extracting {zip_path.name}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    print(f"   → Extracted to {extract_to}")


def detect_language_from_code(code: str) -> str:
    """Heuristic language detection from code content."""
    code_lower = code.lower()
    
    # Go indicators
    if "func " in code and ("package " in code or ":= " in code):
        return "go"
    
    # Python indicators
    if "def " in code and ":" in code:
        return "python"
    if "import " in code and "from " in code:
        return "python"
    
    # TypeScript/JavaScript indicators
    if "const " in code or "let " in code or "function " in code:
        if ": " in code and ("string" in code_lower or "number" in code_lower):
            return "typescript"
        return "javascript"
    
    return "unknown"


def convert_refinement_sample(sample: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a CodeReviewer refinement sample to our format.
    
    CodeReviewer format:
    {
        "old_code": "...",
        "new_code": "...",  
        "comment": "..."
    }
    
    Our format:
    {
        "repo": "codereviewer_dataset",
        "type": "pr_evolution",
        "original_code": "...",
        "reviewer_comment": "...",
        "fixed_code": "...",
        "language": "...",
        "lesson_category": "..."
    }
    """
    original = sample.get("old_code", sample.get("old", ""))
    fixed = sample.get("new_code", sample.get("new", ""))
    comment = sample.get("comment", sample.get("msg", ""))
    
    # Detect language
    language = detect_language_from_code(original + fixed)
    
    # Categorize the comment
    category = categorize_comment(comment)
    
    return {
        "repo": "codereviewer_dataset",
        "pr_number": 0,
        "type": "pr_evolution",
        "file_path": "unknown",
        "original_code": original,
        "reviewer_comment": comment,
        "fixed_code": fixed,
        "lesson_category": category,
        "language": language,
        "quality_score": 50,  # Base score for dataset samples
        "has_vulnerability": False,
        "source": "microsoft_codereviewer",
        "metadata": {}
    }


def categorize_comment(comment: str) -> str:
    """Categorize a comment into lesson type."""
    comment_lower = comment.lower()
    
    if any(p in comment_lower for p in ["security", "vulnerability", "injection"]):
        return "security"
    if any(p in comment_lower for p in ["error", "handle", "exception"]):
        return "error_handling"
    if any(p in comment_lower for p in ["test", "coverage"]):
        return "testing"
    if any(p in comment_lower for p in ["performance", "memory", "optimize"]):
        return "performance"
    if any(p in comment_lower for p in ["refactor", "extract", "interface"]):
        return "architecture"
    if any(p in comment_lower for p in ["style", "naming", "format"]):
        return "style"
    
    return "general"


def process_dataset_file(input_path: Path) -> Iterator[Dict[str, Any]]:
    """Process a dataset file and yield converted samples."""
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                sample = json.loads(line)
                converted = convert_refinement_sample(sample)
                
                # Filter by language if needed
                if converted["language"] in TARGET_LANGUAGES or converted["language"] == "unknown":
                    yield converted
            except json.JSONDecodeError:
                continue


def download_and_convert(output_dir: Path, download_dir: Path = None) -> int:
    """
    Download CodeReviewer dataset and convert to our format.
    
    Returns: Number of samples converted
    """
    if download_dir is None:
        download_dir = output_dir / "raw"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)
    
    total_samples = 0
    
    for dataset_name, url in DATASET_URLS.items():
        print(f"\n{'='*60}")
        print(f"📥 Processing: {dataset_name}")
        print(f"{'='*60}")
        
        # Download
        zip_path = download_dir / f"{dataset_name}.zip"
        if not zip_path.exists():
            print(f"⬇️  Downloading {dataset_name}...")
            download_file(url, zip_path)
        else:
            print(f"✅ Already downloaded: {zip_path}")
        
        # Extract
        extract_dir = download_dir / dataset_name
        if not extract_dir.exists():
            extract_zip(zip_path, extract_dir)
        
        # Find and convert all jsonl files
        output_file = output_dir / f"{dataset_name}_converted.jsonl"
        sample_count = 0
        
        with open(output_file, 'w', encoding='utf-8') as out_f:
            # Search for jsonl or json files in the extracted directory
            for data_file in extract_dir.rglob("*.jsonl"):
                print(f"   Processing: {data_file.name}")
                for sample in process_dataset_file(data_file):
                    json.dump(sample, out_f, ensure_ascii=False)
                    out_f.write('\n')
                    sample_count += 1
            
            for data_file in extract_dir.rglob("*.json"):
                if data_file.suffix == ".json":
                    print(f"   Processing: {data_file.name}")
                    for sample in process_dataset_file(data_file):
                        json.dump(sample, out_f, ensure_ascii=False)
                        out_f.write('\n')
                        sample_count += 1
        
        print(f"✅ Converted {sample_count} samples → {output_file}")
        total_samples += sample_count
    
    print(f"\n{'='*60}")
    print(f"🎉 TOTAL: {total_samples} samples ready for training")
    print(f"{'='*60}")
    
    return total_samples


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Download and convert Microsoft CodeReviewer dataset"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="data/codereviewer",
        help="Output directory for converted JSONL files"
    )
    parser.add_argument(
        "--download-dir",
        type=str,
        default=None,
        help="Directory to store raw downloads (default: output/raw)"
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    download_dir = Path(args.download_dir) if args.download_dir else None
    
    print("🚀 CodeReviewer Dataset Downloader")
    print("   Paper: https://arxiv.org/abs/2203.09095")
    print("   Data:  https://zenodo.org/record/6900648")
    print()
    
    download_and_convert(output_dir, download_dir)


if __name__ == "__main__":
    main()
