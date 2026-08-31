#!/usr/bin/env bash
set -euo pipefail

# Codex CLI のカスタムプロンプトを ~/.codex/prompts/ に展開するユーティリティ。
# `/setup-session-*` のスラッシュプロンプトから最新のセッション資料を参照できる。

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PROMPTS_DIR="$CODEX_HOME/prompts"
SESSIONS=(manager main project)
AGENTS_FILE="$PROJECT_ROOT/AGENTS.md"

if [[ ! -f "$AGENTS_FILE" ]]; then
  echo "[ERROR] Missing $AGENTS_FILE" >&2
  exit 1
fi

mkdir -p "$PROMPTS_DIR"

cat >"$PROMPTS_DIR/setup-session.md" <<'INTRO'
# Setup Session ガイド

Codex CLI でセッション資料を呼び出すには `/setup-session-<session>` の形式を使用します。

```text
/setup-session-manager   # Manager セッション
/setup-session-main      # Main セッション
/setup-session-project   # Project セッション
```

セッション資料を更新した場合はこのスクリプトを再度実行してください。
INTRO

for session in "${SESSIONS[@]}"; do
  output="$PROMPTS_DIR/setup-session-$session.md"
  session_title="${session^}"
  session_upper="${session^^}"
  session_file="$PROJECT_ROOT/.agents/AGENTS_${session_upper}.md"
  claude_file="$PROJECT_ROOT/CLAUDE_${session_upper}.md"

  if [[ ! -f "$session_file" ]]; then
    echo "[ERROR] Missing $session_file" >&2
    exit 1
  fi

  {
    printf '# Setup Session: %s\n\n' "$session_title"
    cat <<HEADER
============================================================
Codex セッション初期化: ${session_title} Session
============================================================

以下のドキュメント内容を Codex CLI のコンテキストに貼り付けてから作業を開始してください。
- リポジトリ共通ルール: AGENTS.md
- セッション詳細ガイド: .agents/AGENTS_${session_upper}.md
- Claude 補足（参考）: CLAUDE_${session_upper}.md (必要に応じて)

------------------------------------------------------------
# AGENTS.md
------------------------------------------------------------
HEADER

    cat "$AGENTS_FILE"

    cat <<SESSIONDOC
------------------------------------------------------------
# .agents/AGENTS_${session_upper}.md
------------------------------------------------------------
SESSIONDOC

    cat "$session_file"

    if [[ -f "$claude_file" ]]; then
      cat <<CLAUDEDOC
------------------------------------------------------------
# CLAUDE_${session_upper}.md (参考: Claude Code 補足)
------------------------------------------------------------
CLAUDEDOC
      cat "$claude_file"
    fi

    cat <<FOOTER
============================================================
コピーが完了したら Codex で作業を開始してください。
============================================================
FOOTER
  } >"$output"

  echo "Generated $output"
done

echo
echo "Codex プロンプトの同期が完了しました。"
