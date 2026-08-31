"""Test helper that loads the production camera service module."""

from importlib import util
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_MODULE_PATH = _PROJECT_ROOT / "camera" / "camera_service.py"

_SPEC = util.spec_from_file_location("camera.camera_service_real", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - defensive
    raise ImportError(f"Cannot locate camera_service.py at {_MODULE_PATH}")

_MODULE = util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

CameraService = getattr(_MODULE, "CameraService")

__all__ = ["CameraService"]
