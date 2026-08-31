"""`scripts/check-basemodel-usage.py` のパス選別と検出のテスト。

このチェックは `/api/v2/app/`（URL の prefix）をファイルパスとして照合していたため、
**1 ファイルもマッチしないまま `✅ All BaseModel imports are using ...` を出して
exit 0** していた。緑が「検査した」の証拠にならない壊れ方なので、
「対象を選べているか」と「違反を落とせるか」の両方を固定する。
"""

import importlib.util
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "check_basemodel_usage", _REPO_ROOT / "scripts" / "check-basemodel-usage.py"
)
cbu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cbu)


class TestShouldCheckFile:
    def test_router_under_api_app_is_checked(self):
        assert cbu.should_check_file(Path("/repo/api/app/routers/outfits.py"))

    def test_url_prefix_path_is_not_a_filesystem_path(self):
        # 実在しない。ここを対象にしていたのが vacuous green の原因
        assert not cbu.should_check_file(Path("/repo/api/v2/app/routers/outfits.py"))

    def test_vendored_venv_is_not_checked(self):
        # api/ 直下に venv が置かれることがある。api/app/ 限定なので拾わない
        assert not cbu.should_check_file(
            Path("/repo/api/.venv/lib/python3.12/site-packages/pydantic/main.py")
        )

    def test_exempt_files_are_skipped(self):
        for exempt in [
            "/repo/api/app/settings.py",
            "/repo/api/app/config.py",
            "/repo/api/app/schemas/base.py",
            "/repo/api/app/__init__.py",
        ]:
            assert not cbu.should_check_file(Path(exempt)), exempt


class TestCheckFile:
    def _write(self, tmp_path, source):
        target = tmp_path / "sample.py"
        target.write_text(textwrap.dedent(source))
        return target

    def test_direct_pydantic_import_is_flagged(self, tmp_path):
        target = self._write(
            tmp_path,
            """
            from pydantic import BaseModel

            class Foo(BaseModel):
                bar: str
            """,
        )
        messages = [m for _, _, m in cbu.check_file(target)]
        assert messages, "直 import を検出できていない"
        assert any("not allowed" in m for m in messages)

    def test_custom_basemodel_import_passes(self, tmp_path):
        target = self._write(
            tmp_path,
            """
            from ..schemas.base import BaseModel

            class Foo(BaseModel):
                bar: str
            """,
        )
        assert cbu.check_file(target) == []


class TestRepositoryIsClean:
    def test_main_returns_zero_and_actually_scans(self, capsys):
        """本体ツリーで違反ゼロ。ただし 0 件走査の緑と区別できないので上のテストと対で見る。"""
        assert cbu.main() == 0
        assert "not found" not in capsys.readouterr().out
