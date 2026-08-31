"""Common path setup module for coordinate_recorder imports."""

import sys
from pathlib import Path


def setup_sys_path():
    """Setup sys.path to include the src directory for coordinate_recorder imports."""
    # Get the path to the src directory
    app_dir = Path(__file__).parent  # api/app/
    api_dir = app_dir.parent  # api/
    project_root = api_dir.parent  # project root
    src_path = project_root / "src"  # src/ directory

    # Add src directory to sys.path if not already present
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    # Also add project root for backward compatibility
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    return src_path, project_root
