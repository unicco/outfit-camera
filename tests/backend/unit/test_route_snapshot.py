"""Route snapshot safety net for the api.py → routers/ migration .

The migration moves endpoint implementations between files and unifies how they
are registered, but it must not change any URL or HTTP method. This test freezes
the app's ``(method, path)`` surface and fails if a migration PR adds, removes,
or renames an endpoint by accident.

What it snapshots: the OpenAPI schema's ``paths`` (``app.openapi()["paths"]``),
i.e. every documented endpoint × method. That is FastAPI's public, version-stable
contract. We deliberately do NOT enumerate ``app.routes`` directly: its internal
representation changed between Starlette 0.52 and 1.3 (included routes moved from
a flat list into ``_IncludedRouter`` wrappers), so the same app yields a wildly
different ``app.routes`` set across versions — a real trap this test hit in CI
(fastapi 0.139 / starlette 1.3.1) while local dev ran fastapi 0.119 / starlette
0.52. The OpenAPI paths are identical across both. Trade-off: the schema omits
FastAPI's built-in docs routes (``/docs``, ``/openapi.json``, ``/redoc``) — those
are framework-provided and untouched by moving api.py handlers, so not guarding
them is fine.

Why a subprocess: ``app.main.app`` is a module-global object that other tests in
the suite may mutate (``dependency_overrides``, routes, ``sys.modules`` mocks),
and under ``pytest -n auto`` it is shared within a worker. Building the schema in
a pristine subprocess (with a PYTHONPATH we set explicitly) measures exactly what
``main.py`` assembles, independent of test ordering.

The feature routers transitively import cv2, which can be unavailable in a
headless CI (missing libGL). When not every feature router loads, the schema is
missing those endpoints and cannot match; the test skips cleanly there and runs
fully wherever the complete dependency set is present (local dev, full test job)
— including on every local ``pytest`` run made while doing the migration, which
is where accidental route changes are actually introduced.

Regenerate the snapshot after an intentional change (e.g. a Phase 2 rename) and
call it out in the PR::

    UPDATE_ROUTE_SNAPSHOT=1 pytest tests/backend/unit/test_route_snapshot.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).with_name("route_snapshot.json")
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Emitted by the subprocess right before its JSON payload so we can ignore any
# unrelated stdout (library banners, warnings) that precedes it.
_MARKER = "<<ROUTE_SNAPSHOT_JSON>>"

# Runs in a fresh interpreter: import the app as main.py assembles it and report
# its OpenAPI endpoint surface plus any feature router that failed to load (see
# module docstring for why this is isolated and schema-based).
_DUMP_PROGRAM = f"""
import json, sys

try:
    import cv2  # noqa: F401
    cv2_status = "ok " + getattr(cv2, "__version__", "?")
except Exception as exc:
    cv2_status = f"{{type(exc).__name__}}: {{exc}}"

import fastapi, starlette
from app.main import ALL_FEATURE_ROUTERS, app, loaded_routers

expected = set(ALL_FEATURE_ROUTERS)
missing = sorted(expected - set(loaded_routers))

pairs = set()
for path, operations in app.openapi().get("paths", {{}}).items():
    for method in operations:
        pairs.add(f"{{method.upper()}} {{path}}")

diag = {{
    "cv2": cv2_status,
    "fastapi": fastapi.__version__,
    "starlette": starlette.__version__,
    "loaded_routers": sorted(loaded_routers),
    "endpoint_count": len(pairs),
}}
sys.stdout.write(
    {_MARKER!r}
    + json.dumps({{"missing": missing, "routes": sorted(pairs), "diag": diag}})
)
"""


def _dump_routes_in_subprocess() -> dict:
    """Return ``{"missing": [...], "routes": [...], "diag": {...}}`` from a fresh interpreter."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(PROJECT_ROOT),
            str(PROJECT_ROOT / "src"),
            str(PROJECT_ROOT / "api"),
            env.get("PYTHONPATH", ""),
        ]
    ).rstrip(os.pathsep)

    proc = subprocess.run(
        [sys.executable, "-c", _DUMP_PROGRAM],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "route-dump subprocess failed to import app.main:\n" + proc.stderr[-4000:]
        )
    if _MARKER not in proc.stdout:
        raise RuntimeError(
            "route-dump subprocess produced no JSON payload; stdout tail:\n"
            + proc.stdout[-2000:]
        )
    return json.loads(proc.stdout.split(_MARKER, 1)[1])


def test_route_snapshot_unchanged() -> None:
    dump = _dump_routes_in_subprocess()
    diag = dump.get("diag", {})

    missing = dump["missing"]
    if missing:
        # Name the actual culprits so a skip is diagnostic: in a headless CI this
        # is the cv2/libGL-dependent routers, but mid-migration it could instead
        # be a router the change accidentally broke — which the reader should see.
        pytest.skip(
            "feature routers failed to load, so the full endpoint surface is "
            f"unavailable: {missing} (in headless CI this is the cv2/libGL-"
            "dependent routers; while migrating, check the router load errors "
            f"in main.py's startup log if this is unexpected) | diag={diag}"
        )

    current = dump["routes"]

    if os.getenv("UPDATE_ROUTE_SNAPSHOT") == "1":
        SNAPSHOT_PATH.write_text(
            json.dumps(current, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"route_snapshot.json regenerated ({len(current)} endpoints)")

    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if current == expected:
        return

    current_set, expected_set = set(current), set(expected)
    added = sorted(current_set - expected_set)
    removed = sorted(expected_set - current_set)
    pytest.fail(
        "Endpoint surface changed vs route_snapshot.json.\n"
        f"  Added ({len(added)}): {added}\n"
        f"  Removed ({len(removed)}): {removed}\n"
        f"  diag: {diag}\n"
        "If this change is intentional (e.g. a Phase 2 rename), regenerate the "
        "snapshot with `UPDATE_ROUTE_SNAPSHOT=1 pytest "
        "tests/backend/unit/test_route_snapshot.py` and call it out in the PR."
    )
