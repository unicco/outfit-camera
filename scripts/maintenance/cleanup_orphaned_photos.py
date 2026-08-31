"""Import-friendly wrapper for the cleanup-orphaned-photos script.

Tests and backend automation expect a snake_case module name, while the CLI
entry point keeps the historical hyphenated filename. We dynamically load the
original script and expose its public API here.
"""

from importlib import machinery, util
from pathlib import Path


_LEGACY_FILENAME = "cleanup-orphaned-photos.py"
_MODULE_NAME = "scripts.maintenance.cleanup_orphaned_photos_cli"

_module_path = Path(__file__).with_name(_LEGACY_FILENAME)

_spec = util.spec_from_file_location(_MODULE_NAME, _module_path)
if _spec is None or _spec.loader is None:
    raise ImportError(
        f"Could not load legacy script module from {_module_path}"  # pragma: no cover
    )

_module = util.module_from_spec(_spec)
machinery.SourceFileLoader(_MODULE_NAME, str(_module_path)).exec_module(_module)

# Re-export everything defined in the legacy script so existing imports keep
# working. The script does not define __all__, so we export non-dunder names.
for name in dir(_module):
    if name.startswith("__"):
        continue
    globals()[name] = getattr(_module, name)

__all__ = [name for name in globals() if not name.startswith("__")]

