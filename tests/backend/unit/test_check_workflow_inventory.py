"""`scripts/ci/check-workflow-inventory.py` の一覧パースと判定のテスト。

README は人間が手で書くので、拡張子つき・バッククォートつき・全角カンマといった表記揺れが
必ず混ざる。揺れで落ちると「README を直しても通らない」状態になり、逃げ道ラベルを持たない
この検査では回避手段が無くなるため、**吸収できていること**を固定する。

同時に、節の外（削除済ワークフローの表）を拾わないことも固定する。拾うと削除済の名前が
「実在しない」として毎回落ちる。
"""

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "check_workflow_inventory",
    _REPO_ROOT / "scripts" / "ci" / "check-workflow-inventory.py",
)
cwi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cwi)


README = """# GitHub Actions Workflows

## ワークフロー一覧（3 個）

| カテゴリ | ワークフロー | トリガー |
|---------|------------|---------|
| CI/テスト | ci-lint-check, test | push/PR |
| doc 検査 | `doc-link-check.yml` | PR |

## doc 検査

### doc-link-check.yml（Doc Link Check）

- **目的**: リンク検査

## 命名規則

- `ci-*`: 継続的インテグレーション

## 削除済ワークフロー

| ワークフロー | 削除時期 | 理由 |
|---|---|---|
| security-snyk-scan | 2026-03 | Dependabot で十分 |
"""


class TestNormalize:
    @pytest.mark.parametrize(
        "raw",
        [
            "ci-lint-check",
            " ci-lint-check ",
            "ci-lint-check.yml",
            "`ci-lint-check.yaml`",
        ],
    )
    def test_variants_collapse_to_the_same_name(self, raw):
        assert cwi.normalize(raw) == "ci-lint-check"


class TestParseListed:
    def test_names_and_count_come_from_the_listing_section(self):
        names, declared = cwi.parse_listed(README)
        assert names == {"ci-lint-check", "test", "doc-link-check"}
        assert declared == 3

    def test_deleted_section_is_not_picked_up(self):
        names, _ = cwi.parse_listed(README)
        # 拾うと「実在しない」として毎回落ちる
        assert "security-snyk-scan" not in names

    def test_header_and_separator_rows_are_dropped(self):
        names, _ = cwi.parse_listed(README)
        assert "ワークフロー" not in names
        assert not any(set(n) <= {"-", ":"} for n in names)

    def test_fullwidth_comma_splits_names(self):
        names, _ = cwi.parse_listed(
            "## ワークフロー一覧（2 個）\n\n| a | foo、bar | c |\n"
        )
        assert names == {"foo", "bar"}

    def test_missing_heading_is_a_format_error(self):
        with pytest.raises(ValueError):
            cwi.parse_listed("# GitHub Actions Workflows\n\n## CI/テスト\n")

    def test_heading_without_count_is_a_format_error(self):
        with pytest.raises(ValueError):
            cwi.parse_listed("## ワークフロー一覧\n\n| a | foo | c |\n")


class TestFindActual:
    def test_yaml_extension_is_included_and_readme_is_not(self, tmp_path):
        (tmp_path / "a.yml").write_text("")
        (tmp_path / "b.yaml").write_text("")
        (tmp_path / "README.md").write_text("")
        assert cwi.find_actual(tmp_path) == {"a", "b"}


def _make_repo(tmp_path: Path, readme: str, names: list[str]) -> Path:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "README.md").write_text(readme, encoding="utf-8")
    for name in names:
        (workflows / f"{name}.yml").write_text("", encoding="utf-8")
    return tmp_path


class TestMain:
    def test_matching_inventory_passes(self, tmp_path, monkeypatch):
        root = _make_repo(tmp_path, README, ["ci-lint-check", "test", "doc-link-check"])
        monkeypatch.setattr(cwi.sys, "argv", ["check", str(root)])
        assert cwi.main() == 0

    def test_undocumented_workflow_fails(self, tmp_path, monkeypatch):
        root = _make_repo(
            tmp_path, README, ["ci-lint-check", "test", "doc-link-check", "venv-audit"]
        )
        monkeypatch.setattr(cwi.sys, "argv", ["check", str(root)])
        assert cwi.main() == 1

    def test_documented_but_missing_file_fails(self, tmp_path, monkeypatch):
        root = _make_repo(tmp_path, README, ["ci-lint-check", "test"])
        monkeypatch.setattr(cwi.sys, "argv", ["check", str(root)])
        assert cwi.main() == 1

    def test_count_mismatch_alone_fails(self, tmp_path, monkeypatch):
        # 名前の集合は一致するが見出しの個数だけ古い、という半端な陳腐化を拾う
        readme = README.replace("（3 個）", "（9 個）")
        root = _make_repo(tmp_path, readme, ["ci-lint-check", "test", "doc-link-check"])
        monkeypatch.setattr(cwi.sys, "argv", ["check", str(root)])
        assert cwi.main() == 1
