"""Logging configuration wrapper for coordinate_recorder modules.

This module provides a simple interface for logging configuration
that wraps the existing logging utilities.
"""

from .logging_utils import setup_logging


def configure_logging() -> None:
    """Configure logging for the application."""
    setup_logging("clothing_detector")
