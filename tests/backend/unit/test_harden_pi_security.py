"""`scripts/setup/harden-pi-security.sh` の回帰テスト。

このスクリプトは 2026-06-04 に、許可する CIDR の取り違えで本番 Pi を完全に
ロックアウトさせている（Tailscale の一時断と重なり microSD の物理復旧が必要
になった・`docs/operations/pi-security-hardening.md`）。会場へ持ち出すために
複数の帯を受けるようにしたので、**同じ失敗形を再現しないこと**を固定する。

守る性質は 4 つ:
- 渡した帯が**全部**、SSH と各サービスポートに入る（1 つでも落ちると繋がらない）
- 旧名 `LAN_CIDR` で呼ばれても、黙って既定へ落とさない（指定したはずの帯が
  許可されないまま気づけないのが 2026-06-04 の形）
- 空・空白のみ・壊れた CIDR・広すぎる帯で**止まる**
- 🚨 **止まるのは `ufw --force reset` より前**。reset は ufw を*無効*にするので、
  そのあとで落ちると `ufw --force enable` に届かず**フィルタが全部外れたまま**残る

`sudo` を差し替えて実スクリプトをそのまま走らせるのは、ロジックを Python に
写すと写し間違いを検出できないテストになるため（`test_prune_stale_venvs.py`
と同じ考え方）。
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HARDEN_SCRIPT = REPO_ROOT / "scripts" / "setup" / "harden-pi-security.sh"

SERVICE_PORTS = ("3000", "8000", "8001", "3100")


def run_harden(
    tmp_path: Path, **env_overrides: str
) -> "tuple[subprocess.CompletedProcess[str], list[str]]":
    """`sudo` と `ufw` を差し替えて実行し、sudo に渡った引数を返す。

    `sudo` の shim が 0 を返すので、sshd_config の書き換えも systemctl も
    素通りする。見たいのは ufw に何をどの順で渡したかだけ。
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "sudo.log"
    (bin_dir / "sudo").write_text(
        f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{log}"\nexit 0\n'
    )
    # `command -v ufw` を通すためだけに置く。実体は sudo 経由でしか呼ばれない
    (bin_dir / "ufw").write_text("#!/usr/bin/env bash\nexit 0\n")
    for name in ("sudo", "ufw"):
        (bin_dir / name).chmod(0o755)

    project = tmp_path / "coordinate-recorder"
    project.mkdir(exist_ok=True)

    env = {k: v for k, v in os.environ.items() if k not in ("LAN_CIDR", "LAN_CIDRS")}
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "HOME": str(tmp_path),
            "PROJECT_ROOT": str(project),
        }
    )
    env.update(env_overrides)

    proc = subprocess.run(
        ["bash", str(HARDEN_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        # 帯の検証は `cd "$PROJECT_ROOT"` より前にあるので、グロブが展開されるのは
        # **起動したときのカレント**。そこを固定しないとグロブの試験ができない
        cwd=tmp_path,
        timeout=60,
    )
    calls = log.read_text().splitlines() if log.exists() else []
    return proc, calls


def allowed_cidrs(calls: list[str], port: str) -> list[str]:
    """そのポートを許可された CIDR を、渡した順で返す。"""
    prefix, suffix = "ufw allow from ", f" to any port {port} proto tcp"
    return [
        call[len(prefix) : -len(suffix)]
        for call in calls
        if call.startswith(prefix) and call.endswith(suffix)
    ]


@pytest.mark.unit
def test_既定では自宅_LAN_だけを許可する(tmp_path: Path) -> None:
    proc, calls = run_harden(tmp_path)

    assert proc.returncode == 0
    assert allowed_cidrs(calls, "22") == ["100.64.0.0/10", "192.168.1.0/24"]
    for port in SERVICE_PORTS:
        assert allowed_cidrs(calls, port) == ["192.168.1.0/24"]


@pytest.mark.unit
def test_複数の帯をすべてのポートに入れる(tmp_path: Path) -> None:
    """会期中は自宅と会場の両方が要る。1 つでも落ちると当日繋がらない。"""
    proc, calls = run_harden(tmp_path, LAN_CIDRS="192.168.1.0/24 192.168.2.0/24")

    assert proc.returncode == 0
    assert allowed_cidrs(calls, "22") == [
        "100.64.0.0/10",
        "192.168.1.0/24",
        "192.168.2.0/24",
    ]
    for port in SERVICE_PORTS:
        assert allowed_cidrs(calls, port) == ["192.168.1.0/24", "192.168.2.0/24"]


@pytest.mark.unit
def test_旧名で呼ばれても指定した帯を使う(tmp_path: Path) -> None:
    """⚠️ 黙って既定へ落とすと、指定したはずの帯が許可されないまま気づけない。"""
    proc, calls = run_harden(tmp_path, LAN_CIDR="10.1.2.0/24")

    assert proc.returncode == 0
    assert allowed_cidrs(calls, "8001") == ["10.1.2.0/24"]
    assert "LAN_CIDRS に変わりました" in proc.stderr


@pytest.mark.unit
def test_両方あるときは新しい名前を採って知らせる(tmp_path: Path) -> None:
    proc, calls = run_harden(
        tmp_path, LAN_CIDR="10.1.2.0/24", LAN_CIDRS="192.168.2.0/24"
    )

    assert proc.returncode == 0
    assert allowed_cidrs(calls, "8001") == ["192.168.2.0/24"]
    assert "無視します" in proc.stderr


@pytest.mark.unit
def test_空文字なら既定へ落とす(tmp_path: Path) -> None:
    """`LAN_CIDRS=` は「指定しなかった」と同じ。ここで止めると、環境変数を
    空にしただけの実行が通らなくなる（空白だけの値とは扱いが違う）。
    """
    proc, calls = run_harden(tmp_path, LAN_CIDRS="")

    assert proc.returncode == 0
    assert allowed_cidrs(calls, "8001") == ["192.168.1.0/24"]


@pytest.mark.unit
def test_グロブがファイル名を帯に化けさせない(tmp_path: Path) -> None:
    """⚠️ 裸の `$LAN_CIDRS` で分割すると、単語分割と一緒にパス名展開まで走る。

    `*/24` はカレントの `10.0.0.0/24` に化け、**書式の検証を通って allow ルールに
    なる**。意図していない帯が黙って開く。パス名展開は実在するものにしか化けない
    ので、その形のファイルを置いて再現する。
    """
    (tmp_path / "10.0.0.0").mkdir()
    (tmp_path / "10.0.0.0" / "24").touch()

    proc, calls = run_harden(tmp_path, LAN_CIDRS="*/24")

    assert proc.returncode != 0
    assert not [call for call in calls if call.startswith("ufw")]


@pytest.mark.unit
def test_境界の_8_は通す(tmp_path: Path) -> None:
    """広さの下限。ここを閉めすぎると 10.0.0.0/8 の LAN で運用できない。"""
    proc, calls = run_harden(tmp_path, LAN_CIDRS="10.0.0.0/8")

    assert proc.returncode == 0
    assert allowed_cidrs(calls, "8001") == ["10.0.0.0/8"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (" ", "空白だけ（`${VAR:-既定}` は非空判定なので既定へ落ちない）"),
        ("192.168.2.0", "プレフィックスが無い"),
        ("192.168.2.0/99", "プレフィックスが範囲外"),
        ("999.1.1.0/24", "オクテットが範囲外"),
        ("10.0.0.0/7", "広すぎる"),
        ("192.168.1.0/24 192.168.2.0", "2 つ目だけ壊れている"),
    ],
)
def test_おかしな帯では_ufw_に触る前に止まる(
    tmp_path: Path, value: str, reason: str
) -> None:
    """🚨 **`ufw --force reset` は ufw を無効にする。**

    そこから先で落ちると `ufw --force enable` に届かず、**フィルタが全部
    外れたまま**残る。だから検証は reset より前で終わらせる。
    """
    proc, calls = run_harden(tmp_path, LAN_CIDRS=value)

    assert proc.returncode != 0, reason
    assert "ERROR" in proc.stderr
    assert not [call for call in calls if call.startswith("ufw")]
