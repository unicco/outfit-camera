#!/usr/bin/env python3
"""venv の実態が requirements ファイルと一致しているかを検査する。

## なぜ必要か

`pip install -r` は **requirements から消えたパッケージを venv から削除しない**。そのため
本番 VPS の venv には、コードから撤去済の依存が残り続ける（2026-07-28 実測で 11 件・
`structlog` / `passlib` / `asyncio-mqtt` / `bcrypt` / dev 用の `pytest` 系）。

残骸そのものより厄介なのは**誰も見ていない**ことで:

  - Dependabot は requirements ファイルしか見ない
  - CI の `dependency-check.yml` も `safety check -r requirements-api.txt` しか見ない

つまり残骸に将来 CVE が出ても、どの自動化にも引っかからない。この検査はその穴を塞ぐ。

## 判定方法: requirements の依存閉包と実インストールを比較する

`pip list --not-required`（＝他パッケージから依存されていないもの）は**使えない**。extras 由来の
依存は依存グラフに載らないため、正しく入っている `uvicorn[standard]` の PyYAML / uvloop /
httptools / websockets / watchfiles や `psycopg[binary]` の psycopg-binary まで「トップレベル」
として出てしまう（2026-07-28 実測で 6 件を誤検知）。

代わりに requirements の各行をルートとして、インストール済メタデータの `Requires-Dist` を
辿った閉包を計算する。extras と環境マーカーは `packaging` で評価するので、
「`uvicorn[standard]` を要求したから PyYAML は正当」「`pytest` は誰も要求していないから残骸」を
区別できる。ネットワークアクセスは無く 1 秒未満で終わる。

## packaging への依存について

`packaging` は `requirements-api.txt` に**直接ピンしてある**。scikit-image 経由の推移的依存に
頼ると、scikit-image を外した瞬間にこの検査が黙って動かなくなるため（のレビュー指摘）。
それでも import できない場合は exit 2（＝検査不能）で明示的に落ちる。「検査できなかった」を
「一致していた」と取り違えないため。

## 使い方

    python3 scripts/maintenance/check_venv_drift.py requirements-api.txt

**検査対象の venv の python で実行すること**（実行中インタプリタの site-packages を見るため）。

    ~/services/coordinate-recorder/.venv/bin/python \\
        scripts/maintenance/check_venv_drift.py requirements-api.txt

`--list-stale` を付けると残骸のパッケージ名だけを改行区切りで出す（掃除スクリプトが
消す対象を機械的に受け取るための口。人間向けの説明は出さない）。

終了コード: 0=一致（--list-stale では常に 0）/ 1=ズレあり / 2=検査不能
"""

from __future__ import annotations

import argparse
import sys
from importlib import metadata
from pathlib import Path

try:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
except ImportError:  # pragma: no cover - 実行環境に packaging が無い場合のみ
    print(
        "ERROR: packaging を import できないため検査できない。\n"
        "  requirements-api.txt に packaging がピンされているか、venv に入っているかを確認すること:\n"
        "    <venv>/bin/pip show packaging",
        file=sys.stderr,
    )
    sys.exit(2)


# venv や pip 自身が管理する道具。requirements に書かれていなくても残骸ではない。
TOOLING = {"pip", "setuptools", "wheel"}


def parse_requirements(path: Path) -> list[Requirement]:
    """requirements ファイルからルート要求を読む。

    行末コメント（`psycopg[binary]==3.3.3  # PostgreSQL adapter`）を落としてからパースする。
    `-r other.txt` のようなオプション行は、このファイル単体の閉包を見る目的から外れるので飛ばす。
    """
    roots = []
    for lineno, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        try:
            roots.append(Requirement(line))
        except Exception as exc:
            print(
                f"ERROR: {path}:{lineno} を解釈できない: {line!r} ({exc})",
                file=sys.stderr,
            )
            sys.exit(2)
    return roots


def requires_of(name: str) -> list[str] | None:
    """インストール済パッケージの Requires-Dist を返す。未インストールなら None。"""
    try:
        return metadata.distribution(name).requires or []
    except metadata.PackageNotFoundError:
        return None


def closure(roots: list[Requirement], lookup=requires_of) -> set[str]:
    """ルート要求から辿れるパッケージ名の集合を返す。

    `(名前, 要求された extras)` の組で訪問済を管理する。同じパッケージでも extras 付きで
    要求されたときは追加の依存が生えるため、名前だけで打ち切ると取りこぼす。

    未インストールのパッケージは依存を辿れない（メタデータが無い）。閉包は「今 venv に入って
    いるものが正当かどうか」の判定にしか使わないので、辿れないものは無視してよい。

    NOTE: ルート行自身のマーカー（`foo; sys_platform == "win32"` のような直接依存）は評価せず、
    無条件に閉包へ入れる。requirements-api.txt に条件付きの直接依存が無いため今は実害が無い。
    そういう行を足すときは、ここでも `r.marker` を評価するように直すこと。
    """
    seen: set[tuple[str, frozenset[str]]] = set()
    queue = [(canonicalize_name(r.name), frozenset(r.extras)) for r in roots]
    while queue:
        key = queue.pop()
        if key in seen:
            continue
        seen.add(key)
        name, extras = key
        specs = lookup(name)
        if specs is None:
            continue
        for spec in specs:
            dep = Requirement(spec)
            if dep.marker is None:
                requested = True
            else:
                # extras 無しで要求された場合も `extra == ""` として評価する必要がある
                # （python_version 等の通常マーカーはこれで正しく評価される）。
                requested = any(
                    dep.marker.evaluate({"extra": e}) for e in (extras or {""})
                )
            if requested:
                queue.append((canonicalize_name(dep.name), frozenset(dep.extras)))
    return {name for name, _ in seen}


def installed_packages() -> dict[str, str]:
    """実行中インタプリタから見えるパッケージを {正規化名: 版} で返す。"""
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            found[canonicalize_name(name)] = dist.version
    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description="venv が requirements と一致しているかを検査する"
    )
    parser.add_argument(
        "requirements", type=Path, help="検査に使う requirements ファイル"
    )
    parser.add_argument(
        "--list-stale",
        action="store_true",
        help="残骸のパッケージ名だけを改行区切りで出力する（掃除スクリプト用）",
    )
    args = parser.parse_args()

    req_path = args.requirements
    if not req_path.is_file():
        print(f"ERROR: {req_path} が無い", file=sys.stderr)
        return 2

    roots = parse_requirements(req_path)
    if not roots:
        print(f"ERROR: {req_path} から要求を 1 つも読めなかった", file=sys.stderr)
        return 2

    keep = closure(roots) | TOOLING
    installed = installed_packages()

    stale = sorted(name for name in installed if name not in keep)
    missing = sorted(
        canonicalize_name(r.name)
        for r in roots
        if canonicalize_name(r.name) not in installed
    )

    if args.list_stale:
        # 掃除スクリプトがそのまま `pip uninstall` に渡す。余計な行を混ぜないこと。
        for name in stale:
            print(name)
        return 0

    print(f"venv: {sys.prefix}")
    print(f"requirements: {req_path}")
    print(
        f"ルート {len(roots)} 件 / 閉包 {len(keep)} 件 / インストール済 {len(installed)} 件"
    )

    if not stale and not missing:
        print("OK: venv は requirements と一致している")
        return 0

    if stale:
        print(f"\n--- requirements の依存閉包に無い（残骸）: {len(stale)} 件 ---")
        for name in stale:
            print(f"  {name}=={installed[name]}")
    if missing:
        print(f"\n--- requirements にあるのに入っていない: {len(missing)} 件 ---")
        for name in missing:
            print(f"  {name}")

    print(
        "\nNG: venv が requirements とズレている。\n"
        "  `pip install -r` は削除しないため、残骸は掃除しないと消えない。直し方:\n"
        "    bash scripts/maintenance/clean-vps-venv.sh            # 検証のみ（本番は無変更）\n"
        "    bash scripts/maintenance/clean-vps-venv.sh --apply    # 残骸を落として入れ替える"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
