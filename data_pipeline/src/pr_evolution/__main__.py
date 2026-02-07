"""
CLI Entry Point for PR Evolution Extractor.

Usage:
    python -m src.pr_evolution.extractor --repo "gofiber/fiber" --output data/
    python -m src.pr_evolution.extractor --all --output data/
"""

import argparse
import sys
from pathlib import Path

from .config import ExtractionConfig, RepoConfig, GOLD_STANDARD_REPOS
from .extractor import PREvolutionExtractor


def main():
    parser = argparse.ArgumentParser(
        description="Extract PR Evolution data for Contextual Architect training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract from a single repo
  python -m src.pr_evolution --repo gofiber/fiber --output data/

  # Extract from all gold-standard repos
  python -m src.pr_evolution --all --output data/

  # Custom extraction with filters
  python -m src.pr_evolution --repo kubernetes/kubernetes --limit 50 --min-comments 3
        """
    )
    
    # Repository selection
    repo_group = parser.add_mutually_exclusive_group(required=True)
    repo_group.add_argument(
        "--repo",
        type=str,
        help="Repository in format 'owner/repo'"
    )
    repo_group.add_argument(
        "--all",
        action="store_true",
        help="Extract from all gold-standard repositories"
    )
    
    # Output configuration
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="data/pr_evolution",
        help="Output directory for JSONL files (default: data/pr_evolution)"
    )
    
    # Extraction filters
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum PRs to extract per repository (default: 100)"
    )
    parser.add_argument(
        "--min-comments",
        type=int,
        default=2,
        help="Minimum review comments required (default: 2)"
    )
    parser.add_argument(
        "--language",
        type=str,
        default="go",
        choices=["go", "python", "typescript", "javascript", "rust"],
        help="Primary language for single repo extraction"
    )
    
    args = parser.parse_args()
    
    # Create configuration
    config = ExtractionConfig(
        min_review_comments=args.min_comments
    )
    
    # Determine repositories to extract from
    if args.all:
        repos = GOLD_STANDARD_REPOS
        print(f"🚀 Extracting from {len(repos)} gold-standard repositories...")
    else:
        # Parse single repo
        try:
            owner, repo = args.repo.split("/")
        except ValueError:
            print(f"❌ Invalid repo format: {args.repo}")
            print("   Use format: owner/repo (e.g., gofiber/fiber)")
            sys.exit(1)
        
        repos = [RepoConfig(owner, repo, args.language, max_prs=args.limit)]
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Run extraction
    print(f"\n📁 Output directory: {output_dir.absolute()}")
    print(f"⚙️  Config: min_comments={config.min_review_comments}")
    print()
    
    extractor = PREvolutionExtractor(config)
    
    try:
        total = extractor.extract_from_multiple_repos(repos, output_dir)
        
        if total > 0:
            print(f"\n✅ Success! {total} training samples ready for fine-tuning.")
            print(f"   Next step: Run the data formatter to prepare for training.")
        else:
            print("\n⚠️  No samples extracted. Try adjusting filters or check GitHub token.")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Extraction interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Extraction failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
