"""markdown の相対リンクが実在するファイルを指しているか検査する。

背景: 1 台構成 → 2 台構成の移行でドキュメントが削除・改称されたのに、参照側が
追随せず 8 本のリンクが誰にも気づかれないまま残っていた。
リポジトリを横断して読む人（と AI）は、切れたリンクを「まだ書かれていない」のか
「移動した」のか区別できない。

検査するのは相対リンクだけ。外部 URL はネットワークに依存して不安定なので見ない。
アンカー（`#見出し`）も見ない。見出しの表記揺れで誤検知が出るわりに、得られる
保証が小さいため。
"""

import re
import sys
from pathlib import Path

# `[表示](path)` の path 部分。`!` 始まりの画像も同じ形なので一緒に拾う。
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# 検査対象から外すディレクトリ。生成物と外部由来のものだけ。
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "dist", "build", "htmlcov"}


def is_relative_link(target: str) -> bool:
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return False
    # `<...>` で囲まれた形や、明らかにパスでないものを除く
    return not target.startswith("<")


def main() -> int:
    # 引数なしなら cwd。CI はリポジトリ直下で走るので指定しない。
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    broken: list[tuple[Path, str]] = []

    for md in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in md.parts):
            continue

        text = md.read_text(encoding="utf-8", errors="replace")
        for raw in LINK_RE.findall(text):
            # `path "title"` 形式の title を落とす
            target = raw.split(" ", 1)[0].strip()
            if not is_relative_link(target):
                continue

            path_part = target.split("#", 1)[0]
            if not path_part:
                continue  # 同一ファイル内アンカーのみ

            if not (md.parent / path_part).exists():
                broken.append((md.relative_to(root), target))

    if not broken:
        print("markdown の相対リンクはすべて実在する")
        return 0

    print(f"リンク切れ {len(broken)} 件:", file=sys.stderr)
    for md_path, target in broken:
        print(f"  {md_path} -> {target}", file=sys.stderr)
    print(
        "\n参照先が消えたなら行ごと消すか後継に差し替える。"
        "まだ書いていないなら Issue にして参照を外す。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
