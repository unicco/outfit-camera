# 依存関係管理ガイド

## 現在の構成

このプロジェクトは pip と requirements.txt を使用して依存関係を管理しています。

- **パッケージ管理**: pip + requirements.txt
- **API 依存関係**: `requirements-api.txt`（版は `==` で固定。基準はファイル冒頭のコメント）
- **開発ツール**: `requirements-dev.txt`（CI 専用。本番 VPS には入れない）
- **Camera 依存関係**: システムパッケージ（apt）+ user site（`~/.local/lib/python3.11/site-packages`）
  - user site の正典は **`camera/pi-user-site.lock`**（推移的依存まで含む完全ロック）
  - `camera/requirements.txt` は**ローカル開発の venv 用**（Python 3.12 前提）。Pi には届かないので版は一致しない
  - `setup-venv.sh` は `requirements-api.txt` → `camera/requirements.txt` の順で**同じ venv**に入れる。共有パッケージの版がズレると後勝ちで上書きされるため、Dependabot は 1 本の group PR で両方を揃える（`dependabot.yml` の updater をルート 1 本にしてある）
  - apt 層（`python3-picamera2` / `python3-libcamera` / `python3-gpiozero` / `python3-lgpio`）はロックの管轄外。Raspberry Pi OS のイメージが提供する

> [!NOTE]
> API は **VPS** で動く（`~/services/coordinate-recorder` の `.venv`）。Pi は **camera 専用**。

## Pi の user site

### なぜロックで、デプロイでの自動 install ではないのか

`deploy/setup-pi.sh` に `pip install --user -r camera/requirements.txt` を足せば「宣言が効く」形にはなる。採らなかった理由は、**Dependabot が上げた無検証の版が毎回のデプロイで本番に入る**ため。毎朝 1 回しかない全身写真の撮影を、検証していない組み合わせに賭けることになる。VPS 側で「venv を作り直すと推移的依存 25 件が無検証で上がる」ことを理由に作り直しを避けたのと同じ判断。

`python3 -m venv --system-site-packages` での venv 化も採らない。`coordinate-camera.service` の ExecStart 変更を伴う本番影響があり、apt の古い版が漏れて隔離も不完全。掃除後の user site が 28 パッケージまで減ったので、得るものが小さい。

結果として Pi は「ロックを git に置き、変更は実機で検証してから反映する」方式にした。ロックが実体と一致していることは `scripts/maintenance/clean-pi-python.sh` が入れ替え後に突き合わせる。

### なぜ拡張子が `.lock` なのか

Dependabot の pip file fetcher（`python/lib/dependabot/python/shared_file_fetcher.rb` の `req_txt_and_in_files`）は `.select { |f| f.name.end_with?(".txt", ".in") }` で候補を絞り、サブディレクトリを 1 階層降りる。つまり `directory: "/"` の updater が `camera/*.txt` まで拾う。

これが原因で、Pi の Python 3.11 に入らない `numpy 2.5.x`（`Requires-Python >=3.12`）が `camera/requirements.txt` に 4 回上がってきた。ignore をパッケージ単位で足す運用は、共有する 8 パッケージ（fastapi / uvicorn / opencv-python / numpy / pillow / piexif / requests / psutil）のどれが次に Python 3.11 を切るか分からない以上、破綻する。

**本番の実体は Dependabot が版を上げてよい対象ではない**ので、拾われない拡張子にした。`.txt` に直すと穴が開く。

代わりに CVE の監視は `dependency-check.yml` の `safety check` が担う。

### 宣言して最初に分かったこと: 本番に既知脆弱性 12 件

ロックを CI に載せた初回（2026-07-29）の `safety check` の結果。

| ファイル | 検出 |
|---|---|
| `requirements-api.txt` | 0 件 |
| `requirements-dev.txt` | 0 件 |
| `camera/requirements.txt` | 0 件 |
| **`camera/pi-user-site.lock`** | **12 件**（starlette 0.47.3 ×6 / pillow 12.1.1 ×5 / requests 2.32.4 ×1） |

Dependabot が追っていた `camera/requirements.txt` は最新版なので 0 件で、その裏で**本番 Pi は古い版のまま 12 件を抱えて動いていた**。宣言していなかった間はこれが誰にも見えていない。

対応は後続の Issue で扱う。版を上げるには Pi 実機での検証が要るため、この方式変更とは切り離す。`safety` の gating 化（`|| true` をやめて赤くする）も、12 件を解消してからでないと常時赤になるので同じ Issue に含める。

### 更新手順

1. Pi を起動して SSH（`ssh user@100.64.0.11`）
2. `bash scripts/maintenance/clean-pi-python.sh` で検証だけ流す（user site は無変更）
3. 通ったら `--apply` で入れ替える
4. 撮影 → VPS アップロード → 検出まで確認する
5. `/usr/bin/python3 -m pip list --user --format=freeze` の出力をロックのヘッダコメントの下に貼ってコミットする

### CI が保証すること・しないこと

`dependency-check.yml` はロックを Python 3.11 で `pip install --dry-run` する。**CI は linux x86_64 で走るので、aarch64 の Pi で入る保証にはならない。** 保証するのは「Python 3.11 で解決できない版が混ざっていないこと」だけ。

## デプロイ時の手順

### 1. 新しい依存関係を追加した場合

`requirements-api.txt` に `==` でピンして追記する（版の決め方は同ファイル冒頭のコメント）。`pip freeze` の出力をそのまま流し込まない（推移的依存まで混ざる）。

```bash
git add requirements-api.txt
git commit -m "chore(deps): add <package>"
git push origin main
```

`requirements-api.txt`（ほか `api/` `src/` `ui/` `deploy/`）が変わると `deploy-vps.yml` が発火し、VPS 上で `deploy/setup-vps.sh` が走って `.venv` に反映される。

> [!WARNING]
> **デプロイが起動したことを必ず確認する。** 2026-07-27 に `requirements-api.txt` を変更した PR（#1677）のマージで、paths 条件を満たしているのに push トリガーの workflow が 1 つも起動しなかった事例がある（手動 dispatch で反映）。**CI が green でもデプロイの成功は意味しない。** 依存の更新は本番の版を直接確認するまで完了ではない。

### 2. 手動で反映する場合

```bash
ssh conoha
cd ~/services/coordinate-recorder
bash deploy/setup-vps.sh                        # 冪等。requirements-api.txt を .venv へ
systemctl --user restart coordinate-api.service
```

systemd unit は `~/.config/systemd/user/coordinate-api.service`（**user unit なので `sudo` 不要**）。

### 3. トラブルシューティング

```bash
systemctl --user status coordinate-api.service
journalctl --user -u coordinate-api.service -n 50
~/services/coordinate-recorder/.venv/bin/pip freeze | grep <package>   # 実際に入っている版
```

`.venv` は `pip install -r` で更新されるため、**requirements から削除したパッケージは残り続ける**。掃除は次節の `clean-vps-venv.sh` で実施する。

## VPS venv の残骸掃除

`deploy/setup-vps.sh` は毎回 `pip install -r requirements-api.txt` を流すだけなので、`requirements-api.txt` から消したパッケージは `.venv` に残り続ける。2026-07-28 実測で 11 件。

- コードから撤去済: structlog / passlib / asyncio-mqtt（+ paho-mqtt）/ bcrypt
- CI でしか使わない dev ツールが古いまま: pytest 7.4.3 / pytest-asyncio 0.21.1 / pytest-cov 4.1.0 / coverage 7.13.4（+ iniconfig / pluggy）

残骸は現時点で既知脆弱性ゼロだが、**requirements に無いパッケージは Dependabot も `dependency-check.yml` も見ていない**ため、将来 CVE が出ても誰も気づけない。未使用の認証系（passlib / bcrypt）が本番に置かれているのも attack surface として望ましくない。

掃除は `scripts/maintenance/clean-vps-venv.sh` を VPS 上で実行する。`deploy-vps.yml` の Check venv drift ステップがデプロイのたびにズレを検出して赤くする（デプロイ本体の後の独立ステップに置いてある。`setup-vps.sh` の中で非ゼロ終了させると `set -e` で health check と UI smoke が走らなくなるため）。**ここが赤いときデプロイ自体は成功している ＝ 直し方は venv の掃除であってリバートではない。**

### なぜ venv を作り直さないのか

当初は「新しい venv に `requirements-api.txt` を入れ直す」つもりだった。以前ピンしたので入り直す版は決定的だと考えたため。

実測したらそうではなかった。ピンされているのは直接依存 30 件だけで、**推移的依存は無ピン**。作り直すと残骸 11 件が消えると同時に**推移的依存 25 件の版が上がる**（cryptography 46→49、protobuf 6→7 のメジャー 2 件を含む）。`requirements-api.txt` 自身のコメントが名指しで警告している「venv を作り直した瞬間に全パッケージが最新へ飛ぶ ＝ 無検証の本番メジャー更新」そのもので、しかも Test Suite の Full ランはその組み合わせを走っていない。

そこで**現在の venv を複製して残骸だけを落とす**方式にした。**版は 1 つも動かない。** 据え置いた推移的依存の版上げは後で精算した（次節）。

「`pip uninstall` は依存関係を考慮しないので消し漏れ・消しすぎる」という弱点は、消す対象を `check_venv_drift.py --list-stale`（requirements の依存閉包の外＝どのパッケージからも要求されていないもの）で機械的に確定させて潰している。手で並べた名前は使わない。

### 方式: 複製して検証してから入れ替える

玄関 Pi の掃除で確立した順序をそのまま使う。あちらは初版が「退避 → 入れ直し → 検証」の順で本番を壊してから確かめ、`simplejpeg` の欠落で camera を止めた。

1. `.venv` を `.venv.stage` に複製する（`.venv` には触らない）
2. 複製側で残骸を uninstall し、import と drift 検査を通す
3. 通ってはじめて入れ替える（`--apply` 指定時のみ）

検証が失敗したら `.venv` には触れずに中止する。API は動き続ける。

`--apply` の停止時間は mv 2 回と再検証だけ（実測 20 秒前後）。venv の中身は複製時点で完成しているので、停止中に pip は動かさない。実行中プロセスを生かしたまま venv を差し替えると遅延 import されるモジュールが消えて実行中に壊れるため、入れ替えの前後で明示的に止めて起こす。

## 推移的依存の版上げと本番の監査

2026-07-29 時点で、本番 venv の実インストール版に既知脆弱性が 12 件（6 パッケージ）あった。`click` / `cryptography` / `httplib2` / `mako` / `pyasn1` / `urllib3` はいずれも推移的依存で、無ピンのため pip の「既存が条件を満たせば据え置く」挙動で古いまま残っていた。解消は #1722。

### 直し方: 脆弱なものだけを直接依存としてピンする

venv は作り直さない。`requirements-api.txt` の基準 2（pip-audit が報告するパッケージは CI 稼働実績版に上げる）を、`starlette` / `packaging` / `scipy` と同じ形で当該パッケージにも適用する。

**ピンを足すと、そのパッケージだけが上がる。** 残りの推移的依存は条件を満たしたまま据え置かれるので、「venv を作り直した瞬間に全部が最新へ飛ぶ」問題は起きない。ピンを足す前に確認すること:

- 新しい版が要求する依存を本番の版が満たすか（満たさないと巻き込みで別のものが上がる）
- 上流の版レンジ上限（`requests` の `urllib3<3` など）に収まるか

### 監査層: VPS の実インストール版を見るのはここだけ

`venv-audit.yml`（毎日 07:30 JST・手動 dispatch 可）が、本番 VPS venv の `pip freeze` を `pip-audit` にかける。

VPS には Pi の `pi-user-site.lock` にあたる完全ロックが無い（`requirements-api.txt` は直接依存だけ）。そのぶん、**実インストール版を見る層がここにしか無い**。

| 仕組み | 見ているもの | VPS の推移的依存の「古い」を検出できるか |
|---|---|---|
| Dependabot | requirements ファイル | ❌ 書かれていないものは見えない |
| `dependency-check.yml` | `safety check` を各 requirements と `pi-user-site.lock` に | ❌ Pi は完全ロックなので見えるが、VPS 側は直接依存だけ |
| venv drift 検査 | requirements に無い**余計な**パッケージ | ❌ 「余計」だけで「古い」は見ない |
| **VPS venv の監査** | 本番 VPS の `pip freeze` 全件 | ✅ |

見つかると**ワークフローが赤くなり Discord へ通知が飛ぶ**。直し方は `requirements-api.txt` にピンを足すこと（前節）。露出しないと判定したものは `deploy/vps-venv-audit-ignore.txt` に ID と理由を書いて黙らせる（理由を書けないものは黙らせない）。

**`deploy-vps.yml` の中に入れていないのは意図的。** Deploy VPS は run 単位の成否が `deploy-drift-check.yml` の「最後の成功デプロイ」判定に使われるため、監査の赤をデプロイの失敗として扱うと毎日 dispatch し直して毎日落ちるループになる（の自己修復と噛み合わない）。独立させたことで、デプロイが無い期間に公開された CVE も拾えるようになっている。

Pi 側はこの監査の対象外。`pi-user-site.lock` が完全ロックなので `dependency-check.yml` の `safety check` が実体の版を見ており、SSH で実機を叩く必要が無い（Pi は撮影後シャットダウンするので毎朝は届かない）。Pi の 12 件は後続で扱う。

## 将来的な改善案

1. **依存関係のキャッシュ**: pip wheel でプリビルド
2. `requirements-api.txt` と `camera/requirements.txt` の既存の食い違い（`fastapi` 0.140.0 対 0.139.2）を揃える。`/camera` updater を外したので、次のルート側 group PR が自動で揃えるはず。揃わなければ手で合わせる
