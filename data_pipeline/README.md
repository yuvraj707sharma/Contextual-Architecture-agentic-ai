# Contextual Architect - Data Pipeline

This module extracts training data for the Contextual Architect AI system.

## Setup

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Set up GitHub token
set GITHUB_TOKEN=your_github_token_here  # Windows
# export GITHUB_TOKEN=your_github_token_here  # Linux/Mac
```

## Usage

### Extract PR Evolution Data
```bash
python -m src.pr_evolution.extractor --repo "gofiber/fiber" --output data/pr_evolution/
```

### Supported Commands
- `--repo`: GitHub repository in format `owner/repo`
- `--output`: Output directory for JSONL files
- `--limit`: Maximum PRs to process (default: 100)
- `--min-comments`: Minimum review comments required (default: 2)

## Output Format

Each extracted PR evolution is saved as JSONL:
```json
{
  "repo": "gofiber/fiber",
  "pr_number": 1234,
  "type": "pr_evolution",
  "original_code": "...",
  "reviewer_comment": "...",
  "fixed_code": "...",
  "lesson": "...",
  "language": "go"
}
```
