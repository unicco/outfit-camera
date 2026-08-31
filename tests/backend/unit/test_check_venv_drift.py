"""venv drift 検査の閉包計算と requirements パースのテスト。

閉包計算は「extras を要求したときだけ extras 依存を辿る」ことが肝で、ここを間違えると
正しく入っている `uvicorn[standard]` の PyYAML 等を残骸と誤検知する（`pip list --not-required`
を使えない理由がこれ）。実インストールのメタデータに依存しないよう lookup を差し替えて検証する。
"""

from pathlib import Path

from packaging.requirements import Requirement

from scripts.maintenance import check_venv_drift as drift

# 依存メタデータのスタブ。値は `importlib.metadata.distribution(name).requires` と同じ形。
FAKE_METADATA = {
    "uvicorn": [
        "click>=7.0",
        'pyyaml>=5.1; extra == "standard"',
        'uvloop; extra == "standard"',
    ],
    "click": [],
    "pyyaml": [],
    "uvloop": [],
    "asyncio-mqtt": ["paho-mqtt>=1.6.0"],
    "paho-mqtt": [],
    "scikit-image": ["lazy-loader>=0.4"],
    "lazy-loader": ["packaging"],
    "packaging": [],
    "legacy-only": ['tomli; python_version < "3.0"'],
}


def fake_lookup(name: str) -> list[str] | None:
    return FAKE_METADATA.get(name)


def closure_of(*specs: str) -> set[str]:
    return drift.closure([Requirement(s) for s in specs], lookup=fake_lookup)


def test_extras_dependencies_are_included_only_when_extras_requested() -> None:
    assert closure_of("uvicorn[standard]==0.41.0") == {
        "uvicorn",
        "click",
        "pyyaml",
        "uvloop",
    }
    assert closure_of("uvicorn==0.41.0") == {"uvicorn", "click"}


def test_transitive_dependencies_are_followed() -> None:
    assert closure_of("scikit-image==0.26.0") == {
        "scikit-image",
        "lazy-loader",
        "packaging",
    }


def test_unrequested_package_and_its_dependency_stay_outside_the_closure() -> None:
    """asyncio-mqtt を要求しなければ、道連れの paho-mqtt も閉包に入らない（＝両方が残骸）。"""
    assert closure_of("uvicorn==0.41.0").isdisjoint({"asyncio-mqtt", "paho-mqtt"})


def test_markers_are_evaluated_against_the_running_environment() -> None:
    """python_version < "3.0" は今のインタプリタでは偽なので辿らない。"""
    assert closure_of("legacy-only==1.0") == {"legacy-only"}


def test_names_are_canonicalized() -> None:
    """`PyYAML` と `pyyaml`、`asyncio_mqtt` と `asyncio-mqtt` を同一視する。"""
    assert closure_of("PyYAML==6.0.3") == {"pyyaml"}
    assert closure_of("asyncio_mqtt==0.16.1") == {"asyncio-mqtt", "paho-mqtt"}


def test_uninstalled_root_does_not_break_the_closure() -> None:
    """メタデータが無いパッケージは依存を辿れないが、閉包計算は続く。"""
    assert closure_of("not-installed==1.0", "click==8.0") == {"not-installed", "click"}


def test_parse_requirements_skips_comments_blank_lines_and_options(
    tmp_path: Path,
) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text(
        "\n".join(
            [
                "# 先頭のコメント",
                "",
                "fastapi==0.140.0",
                "psycopg[binary]==3.3.3  # 行末コメント",
                "-r other-requirements.txt",
                "uvicorn[standard]==0.41.0",
            ]
        ),
        encoding="utf-8",
    )

    roots = drift.parse_requirements(req)

    assert [r.name for r in roots] == ["fastapi", "psycopg", "uvicorn"]
    assert roots[1].extras == {"binary"}
    assert roots[2].extras == {"standard"}
