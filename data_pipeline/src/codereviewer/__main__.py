"""
CLI entry point for CodeReviewer dataset downloader.

Usage:
    python -m src.codereviewer --output data/codereviewer/
"""

from .downloader import main

if __name__ == "__main__":
    main()
