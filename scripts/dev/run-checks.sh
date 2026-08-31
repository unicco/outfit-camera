#!/usr/bin/env bash
# Unified validation entry point for local development before opening a PR.

set -uo pipefail

USER_OVERRIDE_PYTHON="0"
USER_OVERRIDE_UI="0"
USER_OVERRIDE_VITEST_SINCE="0"
SKIP_DB_TESTS="${SKIP_DB_TESTS:-0}"

if [[ -n "${RUN_PYTHON_CHECKS+x}" ]]; then
  USER_OVERRIDE_PYTHON="1"
fi
if [[ -n "${RUN_UI_CHECKS+x}" ]]; then
  USER_OVERRIDE_UI="1"
fi
if [[ -n "${VITEST_CHANGED_SINCE+x}" && -n "${VITEST_CHANGED_SINCE}" ]]; then
  USER_OVERRIDE_VITEST_SINCE="1"
fi

RUN_PYTHON_CHECKS="${RUN_PYTHON_CHECKS:-1}"
RUN_UI_CHECKS="${RUN_UI_CHECKS:-1}"
PYTEST_MARK_EXPRESSION="${PYTEST_MARK_EXPRESSION:-unit and not slow}"
PYTEST_WORKERS="${PYTEST_WORKERS:-auto}"
VITEST_CHANGED_SINCE="${VITEST_CHANGED_SINCE:-}"
VITEST_SCRIPT="${VITEST_SCRIPT:-test:unit:changed}"
RUN_SCOPE_AUTO="0"
RUN_SCOPE_BASE=""

usage() {
  cat <<'EOT'
usage: ./scripts/dev/run-checks.sh [options]

Options:
  --auto-scope           変更ファイルから Python/UI チェックを自動判定
  --base <ref>           自動判定時に比較するベースブランチやコミットを指定
  -h, --help             このヘルプを表示

Environment variables:
  RUN_PYTHON_CHECKS      1 で Python チェック実行 (default: 1)
  RUN_UI_CHECKS          1 で UI チェック実行 (default: 1)
  VITEST_CHANGED_SINCE   Vitest の比較対象 (default: none)
  VITEST_SCRIPT          実行する Vitest スクリプト (default: test:unit:changed)
EOT
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto-scope)
      RUN_SCOPE_AUTO="1"
      shift
      ;;
    --base)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --base requires a value" >&2
        usage
        exit 1
      fi
      RUN_SCOPE_BASE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

export RUN_PYTHON_CHECKS RUN_UI_CHECKS VITEST_CHANGED_SINCE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

RUN_CHECKS_TMP_DIR="${REPO_ROOT}/.tmp/run-checks"
DEFAULT_SQLITE_URL="sqlite:///./.tmp/run-checks/pytest.db"

mkdir -p "${RUN_CHECKS_TMP_DIR}"

if [[ -z "${DATABASE_TEST_URL:-}" ]]; then
  export DATABASE_TEST_URL="${DEFAULT_SQLITE_URL}"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="${DATABASE_TEST_URL}"
fi

PYTHON_TARGETS=(src api camera)

determine_default_base_ref() {
  if [[ -n "${RUN_SCOPE_BASE}" ]]; then
    echo "${RUN_SCOPE_BASE}"
    return
  fi

  if git rev-parse --verify origin/main >/dev/null 2>&1; then
    echo "origin/main"
  elif git rev-parse --verify main >/dev/null 2>&1; then
    echo "main"
  else
    echo ""
  fi
}

apply_auto_scope() {
  local base_ref
  base_ref="$(determine_default_base_ref)"

  if [[ -z "${base_ref}" ]]; then
    echo "[auto-scope] ベースリファレンスが見つからなかったため全チェックを実行します" >&2
    return
  fi

  if ! git rev-parse --verify "${base_ref}" >/dev/null 2>&1; then
    echo "[auto-scope] 指定されたベースリファレンス '${base_ref}' を解決できなかったため全チェックを実行します" >&2
    return
  fi

  local merge_base
  merge_base="$(git merge-base "${base_ref}" HEAD 2>/dev/null || true)"

  if [[ -z "${merge_base}" ]]; then
    echo "[auto-scope] '${base_ref}' との merge-base を取得できなかったため全チェックを実行します" >&2
    return
  fi

  mapfile -t changed_paths < <(git diff --name-only "${merge_base}" || true)

  if [[ "${#changed_paths[@]}" -eq 0 ]]; then
    echo "[auto-scope] 変更されたファイルがないためチェックをスキップします (${merge_base})"
    exit 0
  fi

  local run_python=0
  local run_ui=0

  for path in "${changed_paths[@]}"; do
    case "${path}" in
      src/*|api/*|camera/*|tests/backend/*|tests/unit/*|requirements*.txt|pyproject.toml|setup.py|setup.cfg|Pipfile|poetry.lock|ruff.toml)
        run_python=1
        ;;
      ui/*|tests/frontend/*|ui/package.json|ui/package-lock.json|ui/tsconfig*.json|ui/vite.config.*|package.json|package-lock.json)
        run_ui=1
        ;;
      scripts/dev/run-checks.sh|.github/workflows/ci-lint-check.yml)
        run_python=1
        run_ui=1
        ;;
    esac
  done

  if [[ "${run_python}" == "0" && "${run_ui}" == "0" ]]; then
    echo "[auto-scope] チェック対象の変更がないためスキップしました"
    exit 0
  fi

  if [[ "${USER_OVERRIDE_PYTHON}" != "1" ]]; then
    RUN_PYTHON_CHECKS="${run_python}"
  fi

  if [[ "${USER_OVERRIDE_UI}" != "1" ]]; then
    RUN_UI_CHECKS="${run_ui}"
  fi

  if [[ "${RUN_UI_CHECKS}" == "1" && "${USER_OVERRIDE_VITEST_SINCE}" != "1" ]]; then
    VITEST_CHANGED_SINCE="${merge_base}"
  fi

  export RUN_PYTHON_CHECKS RUN_UI_CHECKS VITEST_CHANGED_SINCE

  echo "[auto-scope] 判定結果 (base: ${merge_base})"
  echo "  - Python checks: ${RUN_PYTHON_CHECKS}"
  echo "  - UI checks: ${RUN_UI_CHECKS}"
  if [[ -n "${VITEST_CHANGED_SINCE}" ]]; then
    echo "  - Vitest changed since: ${VITEST_CHANGED_SINCE}"
  fi
}

ensure_ui_checks_ready() {
  if [[ "${RUN_UI_CHECKS}" != "1" ]]; then
    return
  fi

  if [[ ! -f "ui/package.json" ]]; then
    echo "[warn] ui/package.json が見つからないため UI チェックをスキップします"
    RUN_UI_CHECKS="0"
    export RUN_UI_CHECKS
    return
  fi

  if python - "${VITEST_SCRIPT}" <<'PY'; then
    return
  fi

  echo "[info] ui/package.json に ${VITEST_SCRIPT} スクリプトが見つからないため test:unit にフォールバックします"
  VITEST_SCRIPT="test:unit"
  export VITEST_SCRIPT
PY
import json
import sys
from pathlib import Path

script_name = sys.argv[1]

data = json.loads(Path("ui/package.json").read_text(encoding="utf-8"))
scripts = data.get("scripts", {})

sys.exit(0 if script_name in scripts else 1)
PY
}

if [[ "${RUN_SCOPE_AUTO}" == "1" ]]; then
  echo "[auto-scope] 自動判定モードでチェック対象を解析します"
  apply_auto_scope
fi

ensure_ui_checks_ready

print_hint() {
  case "$1" in
    Ruff*)
      cat <<'EOT'
  Hint: Ruff の E402（"module level import not at top of file"）が頻出する場合は、
  import 文をファイル先頭へ移動するか、必要に応じて `# ruff: noqa: E402` を該当テストに追加してください。
EOT
      ;;
    *)
      ;;  # 一旦汎用ヒントは追加しない
  esac
}

run_step() {
  local label="$1"
  shift

  echo "==> ${label}"
  if "$@"; then
    echo "[PASS] ${label}"
  else
    local status=$?
    echo "[FAIL] ${label} (exit ${status})"
    print_hint "${label}"
    echo "  Retry with: $*"
    exit "${status}"
  fi
  echo
}

if [[ "${RUN_PYTHON_CHECKS}" == "1" ]]; then
  run_step "Ruff (Python lint)" ruff check "${PYTHON_TARGETS[@]}"
  run_step "Black (format check)" black --check "${PYTHON_TARGETS[@]}"
  run_step "MyPy (static typing)" mypy src api
  if [[ "${SKIP_DB_TESTS}" == "1" ]]; then
    echo "[SKIP] Pytest (fast unit subset) - SKIP_DB_TESTS=1"
    echo "  手動実行: pytest -m \"${PYTEST_MARK_EXPRESSION}\" -n ${PYTEST_WORKERS} --ignore=tests/backend/integration --ignore=tests/integration"
  else
    run_step "Pytest (fast unit subset)" \
      pytest \
        -m "${PYTEST_MARK_EXPRESSION}" \
        -n "${PYTEST_WORKERS}" \
        --ignore=tests/backend/integration \
        --ignore=tests/integration
  fi
fi

if [[ "${RUN_UI_CHECKS}" == "1" ]]; then
  run_step "UI ESLint" npm --prefix ui run lint
  run_step "UI Type Check" npm --prefix ui run type-check

  if [[ -n "${VITEST_CHANGED_SINCE}" ]]; then
    run_step "Vitest (changed)" npm --prefix ui run "${VITEST_SCRIPT}" -- "${VITEST_CHANGED_SINCE}"
  else
    run_step "Vitest (changed)" npm --prefix ui run "${VITEST_SCRIPT}"
  fi
fi

echo "All checks completed successfully."
