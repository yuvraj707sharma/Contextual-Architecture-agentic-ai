# Data Pipeline

Data collection and processing for training the Contextual Architect model.

## Modules

### 1. CodeReviewer Dataset (`src/codereviewer/`)
Downloads and converts Microsoft's CodeReviewer dataset from Zenodo.

```bash
# Download and convert (millions of samples)
python -m src.codereviewer --output data/codereviewer/
```

**Paper**: https://arxiv.org/abs/2203.09095  
**Dataset**: https://zenodo.org/record/6900648

### 2. PR Evolution Extractor (`src/pr_evolution/`)
Custom extractor for supplementary training data from specific repositories.

```bash
# Set GitHub token first
$env:GITHUB_TOKEN="your_token"

# Extract from a single repo
python -m src.pr_evolution --repo gofiber/fiber --output data/custom/

# Extract from all gold-standard repos
python -m src.pr_evolution --all --output data/custom/
```

### 3. Shared Utilities (`src/utils.py`)
Common functions used by both modules:
- `detect_language_from_code()` - Language detection (prioritizes file extensions)
- `categorize_comment()` - Classifies review comments by lesson type

## Setup

```bash
python -m venv venv
.\venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

## Output Format

Both modules output the same JSONL schema:
```json
{
  "repo": "gofiber/fiber",
  "type": "pr_evolution",
  "original_code": "...",
  "reviewer_comment": "...",
  "fixed_code": "...",
  "lesson_category": "architecture",
  "language": "go",
  "quality_score": 75
}
```

## Quality Filters

- Minimum comment length: 50 characters
- Minimum quality score: 40/100
- Secret detection (AWS keys, API keys, passwords)
- CVE-affected pattern warnings
