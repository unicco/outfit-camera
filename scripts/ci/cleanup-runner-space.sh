#!/usr/bin/env bash
# Cleanup utilities for GitHub Actions runners.
#
# Used by scheduled jobs that run on persistent runners and tend to exhaust
# disk space (e.g. Weekly Model Retraining). The script supports two modes:
#   - pre  : remove global runner caches before the workflow runs
#   - post : remove workspace artifacts generated during the workflow
#
# Usage:
#   scripts/ci/cleanup-runner-space.sh pre  /path/to/workspace
#   scripts/ci/cleanup-runner-space.sh post /path/to/workspace

set -euo pipefail

MODE="${1:-pre}"
WORKSPACE="${2:-${GITHUB_WORKSPACE:-$(pwd)}}"

log() {
  printf '[cleanup] %s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

cleanup_runner_caches() {
  local runner_root="${RUNNER_ROOT:-/home/runner/actions-runner}"
  local diag_dir="${runner_root}/cached/_diag"

  log "Disk usage before cleanup:"
  df -h || true

  if [[ -d "${diag_dir}" ]]; then
    log "Removing stale runner diagnostics in ${diag_dir}"
    find "${diag_dir}" -type f -mtime +3 -print -delete || true
  fi

  if [[ -d "${runner_root}/_diag" ]]; then
    log "Removing stale runner diagnostics in ${runner_root}/_diag"
    find "${runner_root}/_diag" -type f -mtime +3 -print -delete || true
  fi

  if [[ -d "${HOME}/.cache/pip" ]]; then
    log "Removing pip cache directory to avoid disk bloat"
    rm -rf "${HOME}/.cache/pip"
  fi

  if command -v python3 >/dev/null 2>&1; then
    log "Purging pip wheel cache"
    python3 -m pip cache purge >/dev/null 2>&1 || true
  fi

  if command -v docker >/dev/null 2>&1; then
    log "Pruning unused Docker data"
    docker system prune -af --volumes >/dev/null 2>&1 || true
  fi

  log "Disk usage after runner cache cleanup:"
  df -h || true
}

cleanup_workspace_artifacts() {
  local workspace_path="$1"
  local -a targets=(
    "data/retraining"
    "data/tmp"
    "checkpoints"
    "models"
    "logs"
    ".pytest_cache"
    ".mypy_cache"
  )

  for rel_path in "${targets[@]}"; do
    local full_path="${workspace_path%/}/${rel_path}"
    if [[ -d "${full_path}" || -f "${full_path}" ]]; then
      log "Removing workspace artifact ${full_path}"
      rm -rf "${full_path}"
    fi
  done

  if command -v python3 >/dev/null 2>&1; then
    log "Purging pip wheel cache (post run)"
    python3 -m pip cache purge >/dev/null 2>&1 || true
  fi

  log "Disk usage after workspace cleanup:"
  df -h || true
}

case "${MODE}" in
  pre)
    cleanup_runner_caches
    ;;
  post)
    cleanup_workspace_artifacts "${WORKSPACE}"
    ;;
  *)
    log "Unknown mode: ${MODE}. Use 'pre' or 'post'."
    exit 1
    ;;
esac

