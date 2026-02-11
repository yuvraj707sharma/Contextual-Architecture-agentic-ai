"""
Pytest configuration for data_pipeline tests.

Adds the data_pipeline directory to sys.path for imports.
"""

import sys
from pathlib import Path

# Add data_pipeline to sys.path so we can import from src
data_pipeline_dir = Path(__file__).parent.parent
sys.path.insert(0, str(data_pipeline_dir))
