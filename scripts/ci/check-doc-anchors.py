#!/usr/bin/env python3
"""doc アンカー検査 — アンカーが指すコードを変えたのに doc を更新していない PR を止める。

手順を写した doc は、元のコードが変わっても追随せず、コピペして再実行すると事故を再現する。
経過日数で「doc が古いか」は判定できない（このリポの docs は 8 割が 3 か月超で、閾値を
下げるとノイズになる）。**有効なシグナルは「コードが doc より後に変わった」だけ**なので、
PR の差分で判定する。

## 使い方

doc の中に、その記述が依存しているコードへのアンカーを書く:

    <!-- verify: scripts/setup/harden-pi-security.sh 2026-07-28 -->

パスはリポジトリルートからの相対。日付は「この doc を参照先と突き合わせて確認した日」で、
人間が読むためのもの（この検査では使わない）。

PR が **アンカーの指すパスを変更していて、かつそのアンカーを持つ doc を変更していない**とき、
違反として報告し exit 1 する。

## 識別子で絞る

ファイル単位のアンカーは、巨大なファイルに複数の doc がぶら下がると内容に関係なく全部が
発火する。`#` に続けて識別子をカンマ区切りで並べると、**差分の追加/削除行にその識別子が
現れたときだけ**違反にする:

    <!-- verify: camera/camera_service.py#PIR_DETECTION_WINDOW,_write_backlight 2026-08-10 -->

識別子を書かなければ従来どおりファイル単位。

識別子の選び方:

- doc が**値や名前として写しているもの**を選ぶ（環境変数名・sysfs 属性名・スクリプト名・
  レスポンスのキー）。写した先が変われば doc は必ず腐る
- **定義が 1 箇所しかない名前**を選ぶ。あちこちから呼ばれる公開メソッド名を入れると、
  呼び出し元を消しただけの無関係な PR で発火する
- 列挙から漏れた依存は黙って素通りする（fail-open）。アンカーを足すときは doc がその
  ファイルの何に依存しているかを一度洗い出す

識別子がファイル本文から消えていれば「アンカーの腐り」として常に報告する（リネーム追随）。

## 逃げ道

アンカーは opt-in なので、付けた分しか発火しない＝誤検知は自分で制御できる。
doc の更新が本当に不要な変更は、PR に `docs-not-needed` ラベルを付けて skip する
（workflow 側で判定）。ラベルは job 全体を止めるため、**同じ PR で本当に要る doc の検査も
一緒に消える**。識別子で絞れる場合はラベルより先にそちらを使う。

    python3 scripts/ci/check-doc-anchors.py <base-ref>
"""

import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# <!-- verify: scripts/setup/harden-pi-security.sh 2026-07-28 -->
# <!-- verify: camera/camera_service.py#PIR_GPIO_PIN,_write_backlight 2026-08-10 -->
# 大小文字は問わない（手書きなので Verify: の揺れを黙って無視しないため）
ANCHOR_RE = re.compile(
    r"<!--\s*verify:\s*(?P<path>[^\s#]+)(?:#(?P<idents>\S+))?"
    r"\s+(?P<checked>\d{4}-\d{2}-\d{2})\s*-->",
    re.IGNORECASE,
)

FENCE_RE = re.compile(r"^\s*(```|~~~)")

# リポジトリ全体の .md を対象にする。glob を絞ると api/README.md のような場所に置いた
# アンカーが**無警告で無視される**（保護の穴になる）
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".next"}


def changed_files(base_ref: str) -> set[str]:
    """base_ref との差分で変更されたファイルのリポ相対パス集合。"""
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", f"{base_ref}...HEAD"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        print(f"::error::git diff に失敗した: {result.stderr.strip()}")
        sys.exit(1)
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


@lru_cache(maxsize=None)
def changed_hunk_text(base_ref: str, rel_path: str) -> str:
    """base_ref との差分のうち、rel_path の追加/削除行だけを連結して返す。

    -U0 で文脈行を落とす。文脈行を含めると、隣を直しただけで識別子にマッチしてしまう。
    同じファイルを複数の doc が指すので結果をキャッシュする（引数全体がキー）。
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(REPO_ROOT),
            "diff",
            "-U0",
            f"{base_ref}...HEAD",
            "--",
            rel_path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        print(f"::error::git diff に失敗した: {result.stderr.strip()}")
        sys.exit(1)
    return "\n".join(
        line
        for line in result.stdout.splitlines()
        if line[:1] in {"+", "-"} and not line.startswith(("+++", "---"))
    )


def contains_ident(text: str, ident: str) -> bool:
    """識別子が語として現れるか。

    部分一致だと `discard` が `discarded` を拾う。識別子には `.` や `-` や `/` を含む
    もの（`display-power-helper.py`）があるので \\b ではなく前後の文字種で見る。
    """
    return (
        re.search(rf"(?<![A-Za-z0-9_]){re.escape(ident)}(?![A-Za-z0-9_])", text)
        is not None
    )


def iter_docs():
    for path in sorted(REPO_ROOT.rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        if path.is_file():
            yield path


def anchor_status(
    *,
    path_changed: bool,
    doc_changed: bool,
    idents: list[str],
    file_text: str,
    diff_text: str,
) -> tuple[str, list[str]]:
    """アンカー 1 件の判定。("ok" | "broken" | "violation", 該当した識別子) を返す。

    識別子がファイル本文から消えているときは差分に関係なく broken にする。リネームで
    アンカーが宙に浮いた状態は、その PR で直せる場所が唯一ここだけになるため。
    """
    missing = [ident for ident in idents if not contains_ident(file_text, ident)]
    if missing:
        return "broken", missing
    if not path_changed or doc_changed:
        return "ok", []
    if not idents:
        return "violation", []
    hit = [ident for ident in idents if contains_ident(diff_text, ident)]
    return ("violation", hit) if hit else ("ok", [])


def strip_code_fences(text: str) -> str:
    """コードフェンス内を空行に潰す。

    アンカーの書き方をコードブロックで例示すると、それが本物のアンカーとして拾われて
    無関係な doc の更新を要求してしまう（この doc 自身の説明文がまさにその形）。
    行数は保つ必要がないので、フェンス内は単純に落とす。
    """
    out = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check-doc-anchors.py <base-ref>")
        return 1
    base_ref = sys.argv[1]
    changed = changed_files(base_ref)

    violations: list[tuple[str, str, list[str]]] = []
    broken: list[str] = []
    anchors = 0

    for doc in iter_docs():
        rel_doc = doc.relative_to(REPO_ROOT).as_posix()
        try:
            text = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in ANCHOR_RE.finditer(strip_code_fences(text)):
            rel_path = m.group("path")
            idents = [s for s in (m.group("idents") or "").split(",") if s]
            anchors += 1

            # アンカーが指す先が消えている＝アンカー自体の腐り。これは常に報告する
            target = REPO_ROOT / rel_path
            if not target.exists():
                broken.append(f"{rel_doc} → {rel_path}（参照先が存在しない）")
                continue

            path_changed = rel_path in changed
            status, related = anchor_status(
                path_changed=path_changed,
                doc_changed=rel_doc in changed,
                idents=idents,
                file_text=(
                    target.read_text(encoding="utf-8", errors="replace")
                    if idents
                    else ""
                ),
                diff_text=(
                    changed_hunk_text(base_ref, rel_path)
                    if idents and path_changed
                    else ""
                ),
            )
            if status == "broken":
                broken.append(
                    f"{rel_doc} → {rel_path}#{','.join(related)}"
                    f"（識別子がファイル本文に無い）"
                )
            elif status == "violation":
                violations.append((rel_doc, rel_path, related))

    print(f"doc アンカー: {anchors} 件 / 変更ファイル: {len(changed)} 件")

    for line in broken:
        print(f"::error::アンカーが実物とずれている: {line}")

    for doc_path, code_path, related in violations:
        where = f"{code_path} の {'/'.join(related)}" if related else code_path
        print(
            f"::error file={doc_path}::{where} を変更しているが {doc_path} が更新されていない。"
            f"doc を実物と突き合わせて直し、アンカーの日付を進めること。"
            f"更新が不要なら PR に docs-not-needed ラベルを付ける"
        )

    if violations or broken:
        print()
        print(f"❌ 違反 {len(violations)} 件 / アンカー不整合 {len(broken)} 件")
        return 1

    print("✅ 問題なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
