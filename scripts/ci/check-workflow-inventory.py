"""`.github/workflows/README.md` の一覧と実体の workflow ファイルを突き合わせる。

背景: README が「ワークフロー一覧（9 個）」と書いたまま実体は 16 個で、7 本が丸ごと
未記載・削除済の 1 本が現役として載っていた。誰も突き合わせていないので、
workflow を足しても README は黙って古くなる。

見るのは `## ワークフロー一覧` 節のテーブルだけ。節の外（削除済ワークフローの表、命名規則の
`ci-*`）は拾わないホワイトリスト方式で、README の他の節に何を書いても影響しない。

各 workflow の説明節（`### xxx.yml`）が在るかは**見ない**。一覧に載っているのに説明が無い
状態は通る。README の価値の本体はそちらだが、まずは一覧と実体の集合が一致することだけを
保証する。広げるのは誤検知の出方を見てから。
"""

import re
import sys
from pathlib import Path

# `## ワークフロー一覧（16 個）`。個数も検査対象なので必須にする。
HEADING_RE = re.compile(r"^##\s*ワークフロー一覧（\s*(?P<count>\d+)\s*個\s*）\s*$")

# 節の終わり。次の `##` 見出し（`###` は節の中なので拾わない）。
NEXT_SECTION_RE = re.compile(r"^##(?!#)")

# 名前の区切り。全角カンマ・読点で書かれても拾う。中黒（`・`）やスラッシュは区切りとして
# 扱わない。区切り記号を足し続けると workflow 名に使える文字が減るので、README 側をカンマに
# 合わせる。合っていなければ 1 個の名前として扱われて検査が落ちる（黙って通ることはない）。
NAME_SEP_RE = re.compile(r"[,、，]")


def normalize(name: str) -> str:
    """表記揺れを吸収する。バッククォート・拡張子つきで書かれても同じ名前として扱う。"""
    name = name.strip().strip("`").strip()
    for suffix in (".yml", ".yaml"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.strip()


def parse_listed(text: str) -> tuple[set[str], int]:
    """一覧節から (workflow 名の集合, 見出しに書かれた個数) を返す。

    節が無い / 個数が書かれていない場合は書式エラーとして ValueError を投げる。
    """
    lines = text.splitlines()
    start = None
    declared = 0
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            start = i + 1
            declared = int(m.group("count"))
            break

    if start is None:
        raise ValueError("`## ワークフロー一覧（N 個）` 見出しが見つからない")

    names: set[str] = set()
    for line in lines[start:]:
        if NEXT_SECTION_RE.match(line):
            break
        if not line.lstrip().startswith("|"):
            continue

        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        # 区切り行（`|---|---|`）とヘッダ行を落とす
        if set(cells[1]) <= {"-", ":", " "}:
            continue
        if cells[1] == "ワークフロー":
            continue

        for raw in NAME_SEP_RE.split(cells[1]):
            name = normalize(raw)
            if name:
                names.add(name)

    return names, declared


def find_actual(workflows_dir: Path) -> set[str]:
    """実体の workflow ファイル名（拡張子なし）。`.yaml` で足されても拾う。"""
    return {
        path.stem
        for pattern in ("*.yml", "*.yaml")
        for path in workflows_dir.glob(pattern)
    }


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    workflows_dir = root / ".github" / "workflows"
    readme = workflows_dir / "README.md"

    if not readme.exists():
        print(f"{readme} が無い", file=sys.stderr)
        return 1

    try:
        listed, declared = parse_listed(readme.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"README の書式が壊れている: {e}", file=sys.stderr)
        return 1

    actual = find_actual(workflows_dir)
    missing = sorted(actual - listed)  # 実体はあるが README に載っていない
    stale = sorted(listed - actual)  # README にあるが実体が無い
    count_mismatch = declared != len(actual)

    if not missing and not stale and not count_mismatch:
        print(f"workflow 一覧は実体と一致する（{len(actual)} 個）")
        return 0

    if missing:
        print(f"README の一覧に無い workflow {len(missing)} 件:", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)
    if stale:
        print(f"README にあるが実在しない workflow {len(stale)} 件:", file=sys.stderr)
        for name in stale:
            print(f"  {name}", file=sys.stderr)
    if count_mismatch:
        print(
            f"個数の不一致: 見出しは {declared} 個・実体は {len(actual)} 個",
            file=sys.stderr,
        )

    print(
        "\n`.github/workflows/README.md` の「ワークフロー一覧」節を直す。"
        "workflow を足したなら表への追加と説明節、消したなら「削除済ワークフロー」表への"
        "移動が要る。見出しの個数も合わせる。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
