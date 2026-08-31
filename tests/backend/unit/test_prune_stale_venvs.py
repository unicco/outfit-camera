"""`scripts/maintenance/prune-stale-venvs.sh` の回帰テスト。

venv のパスには requirements のハッシュが埋まるため、requirements を更新するたびに
世代が増え、旧世代は永久に残っていた（2026-08 のローカル実測で 6.2GB の死んだ世代）。
その回収コマンドを追加したが、`rm -rf` を本番 Raspberry Pi でも叩きうるので、
削除範囲と「既定では消さない」ことをテストで固定する。

守る性質は 6 つ:
- 既定は一覧だけ。`--apply` を付けたときだけ消す（誤爆の主因を既定値で潰す）
- 猶予日数より新しい世代は消さない
- チェックアウトの `venv` シンボリックリンクが指す世代は、古くても消さない
- 削除に失敗しても非ゼロ終了しない（掃除の失敗で運用手順が止まらないように）
- 同じ場所を指す置き場を二重に数えない（本番 Pi は HOME が `/home/pi` なので
  走査対象の 2 つ目と 3 つ目が一致する。人間はこの件数と GB を見て `--apply` を
  判断するので、二重計上は判断材料を狂わせる）
- `pyvenv.cfg` を持たないディレクトリは消さない（置き場に紛れ込んだだけの
  無関係なディレクトリを、古いというだけで消さないため）
- `--days` に非数値を渡したら黙って「候補なし」にせず落とす

スクリプトを subprocess で実行するのは、実ファイルをそのまま検証するため。ロジックを
Python 側に写すと、写し間違いを検出できないテストになる。
"""

import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PRUNE_SCRIPT = REPO_ROOT / "scripts" / "maintenance" / "prune-stale-venvs.sh"

DAY_SECONDS = 24 * 60 * 60


def make_venv(base: Path, name: str, age_days: float, *, is_venv: bool = True) -> Path:
    """venv 相当のディレクトリを作る。

    `pyvenv.cfg` は `python3 -m venv` が必ず置く印で、スクリプトはこれを削除の
    前提条件にしている。`is_venv=False` で「置き場に紛れ込んだ無関係な
    ディレクトリ」を再現する。
    """
    path = base / name
    path.mkdir(parents=True)
    if is_venv:
        (path / "pyvenv.cfg").write_text("home = /usr/bin\n")
    mtime = time.time() - age_days * DAY_SECONDS
    os.utime(path, (mtime, mtime))
    return path


def run_prune(
    fake_repo: Path, *args: str, check: bool = True
) -> "subprocess.CompletedProcess[str]":
    """スクリプトを、偽のチェックアウトを PROJECT_ROOT として実行する。

    PROJECT_ROOT はスクリプト自身の位置から決まるので、`scripts/maintenance/` を
    tmp 側に用意して実スクリプトをコピーし、`.venvs/` を走査させる。
    HOME も tmp に振り替えて、実際の ~/.coordinate-recorder-venvs を巻き込まない。
    """
    script_copy = fake_repo / "scripts" / "maintenance" / PRUNE_SCRIPT.name
    script_copy.parent.mkdir(parents=True, exist_ok=True)
    script_copy.write_bytes(PRUNE_SCRIPT.read_bytes())
    script_copy.chmod(0o755)

    fake_home = fake_repo / "fake-home"
    fake_home.mkdir(exist_ok=True)

    return subprocess.run(
        ["bash", str(script_copy), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(fake_home)},
        check=check,
    )


def test_lists_without_deleting_by_default(tmp_path: Path) -> None:
    venvs = tmp_path / ".venvs"
    stale = make_venv(venvs, "api-server-oldhash", age_days=90)

    stdout = run_prune(tmp_path).stdout

    assert stale.is_dir()  # 既定では消さない
    assert "api-server-oldhash" in stdout
    assert "--apply" in stdout


def test_deletes_only_with_apply(tmp_path: Path) -> None:
    venvs = tmp_path / ".venvs"
    stale = make_venv(venvs, "api-server-oldhash", age_days=90)
    fresh = make_venv(venvs, "api-server-newhash", age_days=2)

    run_prune(tmp_path, "--apply")

    assert not stale.exists()
    assert fresh.is_dir()


def test_respects_the_days_window(tmp_path: Path) -> None:
    venvs = tmp_path / ".venvs"
    within = make_venv(venvs, "api-server-a", age_days=40)
    beyond = make_venv(venvs, "api-server-b", age_days=90)

    run_prune(tmp_path, "--apply", "--days", "60")

    assert within.is_dir()  # 60 日の猶予内なので残る
    assert not beyond.exists()


def test_keeps_the_generation_the_checkout_points_at(tmp_path: Path) -> None:
    venvs = tmp_path / ".venvs"
    linked = make_venv(venvs, "api-server-linked", age_days=365)
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    (api_dir / "venv").symlink_to(linked)

    run_prune(tmp_path, "--apply")

    assert linked.is_dir()


def test_counts_a_shared_root_once(tmp_path: Path) -> None:
    """同じ場所を指す 2 つの走査対象を二重に数えない。

    本番 Pi では `$HOME/.coordinate-recorder-venvs` と `/home/pi/.coordinate-recorder-venvs`
    が同一。ここでは HOME 側を `.venvs` への symlink にして同じ状況を作る。
    """
    venvs = tmp_path / ".venvs"
    make_venv(venvs, "api-server-oldhash", age_days=90)

    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".coordinate-recorder-venvs").symlink_to(venvs)

    stdout = run_prune(tmp_path).stdout

    assert stdout.count("api-server-oldhash") == 1
    assert "1 件" in stdout


def test_never_touches_a_directory_without_a_venv_marker(tmp_path: Path) -> None:
    """置き場に紛れ込んだ無関係なディレクトリを消さない。

    走査対象は共有の置き場なので、venv 以外が置かれる余地がある。年齢だけで
    `rm -rf` すると、それが単なるディスク回収ではなくデータ消失になる。
    """
    venvs = tmp_path / ".venvs"
    not_a_venv = make_venv(venvs, "some-old-backup", age_days=365, is_venv=False)
    (not_a_venv / "大事なもの.txt").write_text("消えては困る")
    # 中にファイルを置くとディレクトリの mtime が今になり、そもそも候補から外れて
    # しまう。年齢の条件は満たしたうえで pyvenv.cfg だけが無い状態にする
    old = time.time() - 365 * DAY_SECONDS
    os.utime(not_a_venv, (old, old))

    real_venv = make_venv(venvs, "api-server-oldhash", age_days=365)

    stdout = run_prune(tmp_path, "--apply").stdout

    assert not_a_venv.is_dir()
    assert (not_a_venv / "大事なもの.txt").exists()
    assert "venv ではない" in stdout
    assert not real_venv.exists()  # 本物の venv は消える


def test_keeps_going_when_a_generation_cannot_be_removed(tmp_path: Path) -> None:
    """削除できない世代があっても非ゼロ終了しない。

    運用手順の途中で止まると、残りの世代が回収されないまま人間が気づけない。
    """
    venvs = tmp_path / ".venvs"
    undeletable = make_venv(venvs, "api-server-locked", age_days=90)
    venvs.chmod(0o500)  # 読み取り・実行のみ。エントリの削除ができない

    try:
        stdout = run_prune(tmp_path, "--apply").stdout
    finally:
        venvs.chmod(0o700)

    assert "削除できず" in stdout
    assert undeletable.is_dir()


def test_rejects_a_non_numeric_days_value(tmp_path: Path) -> None:
    make_venv(tmp_path / ".venvs", "api-server-oldhash", age_days=90)

    result = run_prune(tmp_path, "--days", "abc", check=False)

    assert result.returncode != 0
    assert "--days" in result.stderr


def test_is_quiet_when_there_is_nothing_to_reclaim(tmp_path: Path) -> None:
    make_venv(tmp_path / ".venvs", "api-server-fresh", age_days=1)

    stdout = run_prune(tmp_path).stdout

    assert "ありません" in stdout
