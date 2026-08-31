"""`systemd/scripts/kiosk-health-monitor.sh` の回帰テスト。

この監視スクリプトは玄関 Pi の常駐プロセスで、判定を誤ると**毎分キオスクを再起動する**。
実際、UI が VPS 配信に移ったあとも `localhost:3000` と `coordinate-ui.service` を見続け、
数か月ぶん誤検知を出していた。人間が気づけるのは実機の journal だけだったので、
判定の性質をここで固定する。

守る性質は 6 つ:
- ブラウザが生きているうちは再起動を打たない（誤爆が最悪の事故）
- PID が別プロセスへ再利用されても「生きている」と答えない（沈黙する監視を作らない）。
  再利用先がたまたま chromium でも、キオスクでなければ生存とみなさない
- PID ファイルを失っても、キオスクのブラウザが実在するなら再起動しない
- 起動処理中（新しいロックがある）は判定を保留する。`wait_for_touchscreen` は UI が
  不通だと数分ブロックするため、待ちの最中に再起動すると振り出しに戻り続ける
- 本当に不在なら 3 サイクル待って再起動する（後詰め。キオスク本体も自力で復帰を試みる）

スクリプトを subprocess で実行するのは、実ファイルをそのまま検証するため。ロジックを
Python 側に写すと、写し間違いを検出できないテストになる。`systemctl` / `sudo` / `curl` /
`pgrep` / `sleep` は PATH のスタブに差し替え、ループを実時間で待たずに回す。
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MONITOR_SCRIPT = REPO_ROOT / "systemd" / "scripts" / "kiosk-health-monitor.sh"

RESTART_MARKER = "STUB-sudo systemctl restart coordinate-kiosk.service"


def write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/bash\n" + body)
    path.chmod(0o755)


def make_stubs(directory: Path, *, browser_running: bool) -> None:
    """監視ループが叩く外部コマンドを差し替える。

    `sleep` を no-op にすることでループが実時間を待たずに回る。`curl` はカメラの
    `/stream` にだけ成功を返し、カメラ再起動の判定がテストに混ざらないようにする。
    """
    write_stub(directory, "sleep", "exit 0\n")
    write_stub(directory, "systemctl", "exit 0\n")
    write_stub(directory, "sudo", '[ "$1" = "-n" ] && shift\necho "STUB-sudo $*"\nexit 0\n')
    write_stub(
        directory,
        "curl",
        'for a in "$@"; do case "$a" in */stream) echo "Content-Type: image/jpeg"; exit 0;; esac; done\nexit 22\n',
    )
    write_stub(directory, "pgrep", "exit 0\n" if browser_running else "exit 1\n")


def run_monitor(
    tmp_path: Path,
    *,
    pid_file: Path | None = None,
    lock_file: Path | None = None,
    browser_running: bool = False,
    want_lines: int = 14,
    timeout: float = 20.0,
) -> str:
    """監視ループを一定行ぶんだけ回して出力を返す（ループは無限なので打ち切る）。"""
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    make_stubs(stub_dir, browser_running=browser_running)

    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}:{env['PATH']}"
    env["BROWSER_PID_FILE"] = str(pid_file) if pid_file else str(tmp_path / "absent.pid")
    env["BROWSER_LOCK_FILE"] = str(lock_file) if lock_file else str(tmp_path / "absent.lock")
    # 実機の既定値（VPS 配信）に依存させない
    env["UI_URL"] = "http://127.0.0.1:9/touchscreen"

    proc = subprocess.Popen(
        ["bash", str(MONITOR_SCRIPT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    lines: list[str] = []
    deadline = time.time() + timeout
    try:
        while len(lines) < want_lines and time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            lines.append(line)
    finally:
        proc.kill()
        proc.wait(timeout=10)
    return "".join(lines)


def spawn_fake_process(argv0: str) -> subprocess.Popen:
    """指定したコマンドラインを持つ生きたプロセスを作る（`exec -a` で argv[0] を差し替え）。"""
    return subprocess.Popen(["bash", "-c", f'exec -a "{argv0}" sleep 60'])


@pytest.fixture
def live_browser():
    """キオスクのブラウザ相当のプロセス。PID の生存だけでなくコマンドラインまで
    見ていることを、実プロセスで確かめるため。"""
    proc = spawn_fake_process("/usr/bin/chromium --kiosk http://example/touchscreen")
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait(timeout=10)


@pytest.fixture
def unrelated_chromium():
    """キオスクではない chromium（`--kiosk` を持たない）。"""
    proc = spawn_fake_process("/usr/bin/chromium https://example.com")
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait(timeout=10)


@pytest.mark.unit
def test_live_browser_is_not_restarted(tmp_path: Path, live_browser: int) -> None:
    pid_file = tmp_path / "kiosk-browser.pid"
    pid_file.write_text(f"{live_browser}\n")

    output = run_monitor(tmp_path, pid_file=pid_file)

    assert RESTART_MARKER not in output
    assert "Kiosk browser process not found" not in output


@pytest.mark.unit
def test_recycled_pid_is_not_treated_as_alive(tmp_path: Path) -> None:
    """PID ファイルが chromium 以外のプロセスを指すなら「生きている」と答えない。"""
    pid_file = tmp_path / "kiosk-browser.pid"
    pid_file.write_text(f"{os.getpid()}\n")  # pytest 自身。chromium ではない

    output = run_monitor(tmp_path, pid_file=pid_file)

    assert RESTART_MARKER in output


@pytest.mark.unit
def test_recycled_pid_on_unrelated_chromium_is_not_treated_as_alive(
    tmp_path: Path, unrelated_chromium: int
) -> None:
    """再利用先がたまたま chromium でも、キオスクでなければ「生きている」と答えない。"""
    pid_file = tmp_path / "kiosk-browser.pid"
    pid_file.write_text(f"{unrelated_chromium}\n")

    output = run_monitor(tmp_path, pid_file=pid_file)

    assert RESTART_MARKER in output


@pytest.mark.unit
def test_stale_pid_file_with_running_browser_does_not_restart(tmp_path: Path) -> None:
    """PID ファイルを失っても、キオスクのブラウザが実在するなら画面を触らない。"""
    output = run_monitor(tmp_path, browser_running=True)

    assert RESTART_MARKER not in output
    assert "skipping restart" in output


@pytest.mark.unit
def test_launch_in_progress_defers_judgement(tmp_path: Path) -> None:
    """起動処理中は不在と数えない（待ちの最中に再起動すると振り出しに戻る）。"""
    lock_file = tmp_path / "kiosk-browser.lock"
    lock_file.touch()

    output = run_monitor(tmp_path, lock_file=lock_file)

    assert RESTART_MARKER not in output
    assert "deferring browser check" in output


@pytest.mark.unit
def test_stale_lock_does_not_defer_forever(tmp_path: Path) -> None:
    """猶予を過ぎたロックは保留の根拠にしない（起動に失敗したまま放置しない）。"""
    lock_file = tmp_path / "kiosk-browser.lock"
    lock_file.touch()
    old = time.time() - 3600
    os.utime(lock_file, (old, old))

    output = run_monitor(tmp_path, lock_file=lock_file)

    assert RESTART_MARKER in output


@pytest.mark.unit
def test_restart_waits_three_cycles(tmp_path: Path) -> None:
    """1 サイクル目では再起動しない（瞬間的な不在で画面を飛ばさない）。"""
    output = run_monitor(tmp_path, want_lines=4)

    assert "(1/3 before restart)" in output
    assert RESTART_MARKER not in output
