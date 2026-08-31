"""`scripts/ci/check-doc-anchors.py` のアンカー解析と判定のテスト。

ファイル単位のアンカーは、3000 行の `camera/camera_service.py` に 2 つの doc がぶら下がって
いたため内容に関係なく必ず発火し、逃げ道の `docs-not-needed` が常用されて検査ごと止まって
いた。識別子で絞る判定を入れたので、**絞れていること**と**絞りすぎて素通り
しないこと**の両方を固定する。
"""

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "check_doc_anchors", _REPO_ROOT / "scripts" / "ci" / "check-doc-anchors.py"
)
cda = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cda)


def parse(text: str):
    """アンカー 1 件を (path, idents) に分解する。"""
    m = cda.ANCHOR_RE.search(text)
    assert m is not None, text
    return m.group("path"), [s for s in (m.group("idents") or "").split(",") if s]


class TestAnchorRe:
    def test_plain_anchor_has_no_idents(self):
        assert parse("<!-- verify: deploy/setup-pi.sh 2026-08-01 -->") == (
            "deploy/setup-pi.sh",
            [],
        )

    def test_idents_are_split_on_comma(self):
        path, idents = parse(
            "<!-- verify: camera/camera_service.py#PIR_GPIO_PIN,_write_backlight 2026-08-10 -->"
        )
        assert path == "camera/camera_service.py"
        assert idents == ["PIR_GPIO_PIN", "_write_backlight"]

    def test_idents_may_contain_dot_hyphen_slash(self):
        # display-power-helper.py や /pir/status をそのまま書ける必要がある
        _, idents = parse(
            "<!-- verify: camera/camera_service.py#display-power-helper.py,/pir/status 2026-08-10 -->"
        )
        assert idents == ["display-power-helper.py", "/pir/status"]

    def test_date_is_still_required(self):
        assert (
            cda.ANCHOR_RE.search("<!-- verify: camera/camera_service.py#FOO -->")
            is None
        )

    def test_repo_anchors_all_parse(self):
        """実在のアンカーが 1 件も取りこぼされないこと（書式ミスの検出）。"""
        found = 0
        for doc in cda.iter_docs():
            text = cda.strip_code_fences(doc.read_text(encoding="utf-8"))
            found += len(list(cda.ANCHOR_RE.finditer(text)))
        assert found >= 8


class TestContainsIdent:
    def test_matches_whole_word(self):
        assert cda.contains_ident("    self.discard_photo(name)", "discard_photo")

    def test_does_not_match_substring(self):
        assert not cda.contains_ident("+ discarded = True", "discard")

    def test_does_not_match_longer_identifier(self):
        assert not cda.contains_ident("+ PIR_GPIO_PIN_ALT = 1", "PIR_GPIO_PIN")

    def test_dotted_name_matches(self):
        assert cda.contains_ident(
            '+ "display-power-helper.py"', "display-power-helper.py"
        )

    def test_slashed_route_matches(self):
        assert cda.contains_ident('+@app.get("/pir/status")', "/pir/status")


class TestAnchorStatus:
    def _status(self, **kwargs):
        base = {
            "path_changed": True,
            "doc_changed": False,
            "idents": [],
            "file_text": "",
            "diff_text": "",
        }
        return cda.anchor_status(**{**base, **kwargs})

    def test_unchanged_path_is_ok(self):
        assert self._status(path_changed=False) == ("ok", [])

    def test_updated_doc_is_ok(self):
        assert self._status(doc_changed=True) == ("ok", [])

    def test_file_level_anchor_fires_on_any_change(self):
        assert self._status() == ("violation", [])

    def test_ident_anchor_is_silent_when_diff_misses_it(self):
        # 本題。PIR と無関係な変更で pir doc を要求されていた
        status, related = self._status(
            idents=["PIR_GPIO_PIN"],
            file_text="PIR_GPIO_PIN = 18",
            diff_text="+    self._clear_unsent(filename)",
        )
        assert (status, related) == ("ok", [])

    def test_ident_anchor_fires_when_diff_hits_it(self):
        status, related = self._status(
            idents=["PIR_GPIO_PIN", "_write_backlight"],
            file_text="PIR_GPIO_PIN = 18\ndef _write_backlight(self): ...",
            diff_text='-    os.environ.get("PIR_GPIO_PIN", "18")',
        )
        assert (status, related) == ("violation", ["PIR_GPIO_PIN"])

    def test_missing_ident_is_broken_even_without_changes(self):
        # リネームでアンカーが宙に浮いた状態。差分に関係なく報告する
        status, related = self._status(
            path_changed=False,
            idents=["PIR_GPIO_PIN", "gone_away"],
            file_text="PIR_GPIO_PIN = 18",
        )
        assert (status, related) == ("broken", ["gone_away"])

    def test_missing_ident_wins_over_doc_update(self):
        status, _ = self._status(doc_changed=True, idents=["gone"], file_text="")
        assert status == "broken"


class TestRepoAnchorsResolve:
    """実在のアンカーの参照先と識別子が今のコードに存在すること。"""

    @pytest.mark.parametrize(
        "doc_rel",
        ["docs/deployment/pir-display-control.md", "docs/operations/monitoring.md"],
    )
    def test_idents_exist_in_target(self, doc_rel):
        text = cda.strip_code_fences((_REPO_ROOT / doc_rel).read_text(encoding="utf-8"))
        for m in cda.ANCHOR_RE.finditer(text):
            target = _REPO_ROOT / m.group("path")
            assert target.exists(), m.group("path")
            file_text = target.read_text(encoding="utf-8", errors="replace")
            for ident in (m.group("idents") or "").split(","):
                if ident:
                    assert cda.contains_ident(file_text, ident), ident
