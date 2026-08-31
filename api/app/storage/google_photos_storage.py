import os
import secrets
import tempfile
import threading
import time
import logging
from typing import Optional
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import requests

from ..url_safety import is_allowed_storage_url
from .base_storage import BaseStorageHandler

logger = logging.getLogger(__name__)

# OAuth の consent 完了までに許す時間。これを過ぎた state は無効（CSRF/リプレイ対策）。
STATE_TTL_SECONDS = 600

# 保留中 state の上限。/auth-url は無認証のため、TTL 内に大量呼び出しされても
# メモリが青天井にならないよう、超過時は失効が近い順に間引く（DoS 緩和）。
MAX_PENDING_STATES = 100


class GooglePhotosStorageHandler(BaseStorageHandler):
    """Google Photos へのアップロード機能を提供するストレージハンドラー."""

    def __init__(self):
        self.credentials_file = os.getenv(
            "GOOGLE_CREDENTIALS_FILE", "google_photos_credentials.json"
        )
        self.token_file = os.getenv("GOOGLE_TOKEN_FILE", "google_photos_token.json")
        self.album_name = os.getenv("GOOGLE_PHOTOS_ALBUM_NAME", "Coordinate Records")
        # 追加先アルバムの ID。呼び出し側が album_id を渡さないときはこれを使う。
        # 名前から引く create_album() は albums().list() を叩くが、そちらは現行スコープでは
        # 403 になる（下の create_album() のコメント）。ID 直指定なら appendonly だけで通る。
        self.batch_album_id = os.getenv("GOOGLE_PHOTOS_BATCH_ALBUM_ID", "")
        self.scopes = [
            "https://www.googleapis.com/auth/photoslibrary",
            "https://www.googleapis.com/auth/photoslibrary.appendonly",
            "https://www.googleapis.com/auth/photoslibrary.sharing",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "openid",
            "https://www.googleapis.com/auth/calendar.readonly",
        ]
        self.max_retries = int(os.getenv("GOOGLE_PHOTOS_MAX_RETRIES", "3"))
        self.retry_delay = float(os.getenv("GOOGLE_PHOTOS_RETRY_DELAY", "1.0"))
        # OAuth の state → (redirect_uri, code_verifier, 失効時刻[monotonic]) の対応。
        # 単一プロセス内メモリのため、将来マルチワーカー化する場合は Redis 等へ移す。
        self._pending_states: dict[str, tuple[str, Optional[str], float]] = {}
        self._state_lock = threading.Lock()

    def get_photo_url(self, photo_id: str) -> str:
        """写真のURLを取得（Google Photos では直接URL取得は制限されるため、基本的にはプレースホルダー）."""
        return f"https://photos.google.com/{photo_id}"

    def get_file_url(self, photo_uuid: str) -> str:
        """ファイルの URL を取得（データベース保存用）."""
        return f"googlephotos://{photo_uuid}"

    def validate_photo_id(self, photo_id: str) -> str:
        """写真 ID を検証してクリーンアップ."""
        return photo_id.strip()

    def _write_token(self, token_json: str) -> None:
        """トークン JSON を 0600 で保存する（作成時から他ユーザーに読ませない）."""

        def _opener(path: str, flags: int) -> int:
            return os.open(path, flags, 0o600)

        with open(self.token_file, "w", opener=_opener) as token_file:
            token_file.write(token_json)
        # 既存ファイルを上書きした場合に備えて明示的に権限も締める
        os.chmod(self.token_file, 0o600)

    def _register_state(
        self, state: str, redirect_uri: str, code_verifier: Optional[str]
    ) -> None:
        """OAuth state を登録する（期限切れは登録時に掃除）.

        ``code_verifier`` も持たせるのは、コールバック側が Flow を作り直すため
        （PKCE の verifier は Flow インスタンスにしか無く、渡さないと
        ``invalid_grant: Missing code verifier`` で必ず失敗する）。
        """
        expiry = time.monotonic() + STATE_TTL_SECONDS
        with self._state_lock:
            self._prune_expired_states_locked()
            # 期限切れ掃除後もなお上限超過なら、失効が近い順に間引く。
            while len(self._pending_states) >= MAX_PENDING_STATES:
                oldest = min(
                    self._pending_states, key=lambda s: self._pending_states[s][2]
                )
                del self._pending_states[oldest]
            self._pending_states[state] = (redirect_uri, code_verifier, expiry)

    def _consume_state(self, state: str) -> Optional[tuple[str, Optional[str]]]:
        """state を検証してワンタイム消費し、``(redirect_uri, code_verifier)`` を返す.

        未知・期限切れの state は ``None`` を返す（呼び出し側で拒否する）。
        """
        with self._state_lock:
            self._prune_expired_states_locked()
            entry = self._pending_states.pop(state, None)
        if entry is None:
            return None
        redirect_uri, code_verifier, _expiry = entry
        return redirect_uri, code_verifier

    def _prune_expired_states_locked(self) -> None:
        """期限切れ state を削除する（``_state_lock`` 保持中に呼ぶこと）."""
        now = time.monotonic()
        expired = [
            s
            for s, (_uri, _verifier, exp) in self._pending_states.items()
            if exp <= now
        ]
        for state in expired:
            del self._pending_states[state]

    def get_credentials(self) -> Optional[Credentials]:
        """Google Photos API の認証情報を取得."""
        creds = None
        token_path = Path(self.token_file)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Token refresh failed: {e}")
                    return None
            else:
                return None

        return creds

    def initiate_auth_flow(
        self, redirect_uri: str = "http://localhost:8080/oauth2callback"
    ) -> str:
        """OAuth 2.0 認証フローを開始し、認証URLを返す."""
        if not Path(self.credentials_file).exists():
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_file}"
            )

        flow = Flow.from_client_secrets_file(
            self.credentials_file, scopes=self.scopes, redirect_uri=redirect_uri
        )

        # CSRF 対策の state を発行し、authorize URL に埋め込む。
        # コールバックはこの state を返し、_consume_state で照合する。
        state = secrets.token_urlsafe(32)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="false",  # 同意は本クライアントの要求スコープのみに限定（incremental auth で他スコープを引き込まない）
            prompt="consent",  # refresh_token を確実に取得
            state=state,
        )

        # Flow が自動生成した PKCE の verifier を state と一緒に預ける。
        # authorization_url() の後でないと生成されていない。
        self._register_state(state, redirect_uri, getattr(flow, "code_verifier", None))

        return auth_url

    def complete_auth_flow(
        self, authorization_code: str, state: str, redirect_uri: Optional[str] = None
    ) -> bool:
        """認証コードと state を使用して認証フローを完了.

        ``state`` は ``initiate_auth_flow`` が発行したものと一致する必要がある
        （ログイン CSRF 対策）。一致しない・期限切れの場合は認証を拒否する。
        ``redirect_uri`` 引数は後方互換のため残すが、実際には state 登録時の値を使う。
        """
        try:
            if not state:
                logger.warning("OAuth callback rejected: missing state parameter")
                return False

            consumed = self._consume_state(state)
            if consumed is None:
                logger.warning(
                    "OAuth callback rejected: unknown or expired state parameter"
                )
                return False

            # state 登録時の redirect_uri を権威として使う（引数の redirect_uri は無視）。
            # authorize URL 生成時と同じ値を使わないと Google 側で redirect_uri_mismatch になる。
            redirect_uri, code_verifier = consumed

            if not Path(self.credentials_file).exists():
                raise FileNotFoundError(
                    f"Credentials file not found: {self.credentials_file}"
                )

            flow = Flow.from_client_secrets_file(
                self.credentials_file, scopes=self.scopes, redirect_uri=redirect_uri
            )
            # 作り直した Flow は PKCE の verifier を持たない。authorize 時のものを
            # 戻さないと Google が invalid_grant で弾く。
            flow.code_verifier = code_verifier

            flow.fetch_token(code=authorization_code)

            creds = flow.credentials

            # トークンを保存（refresh_token を含むため所有者のみ読み書き可・0600 で作成）
            self._write_token(creds.to_json())

            return True

        except Exception as e:
            logger.error(f"Auth flow completion failed: {e}")
            return False

    def is_authenticated(self) -> bool:
        """Google Photos API の認証状態を確認."""
        creds = self.get_credentials()
        return creds is not None and creds.valid

    def create_album(self, album_name: str = None) -> Optional[str]:
        """アルバム名から ID を引く（無ければ作る）。

        ⚠️ **現行のスコープでは albums().list() が必ず 403 になる**ので、この経路は
        実質使えない。Google が 2025-03-31 に photoslibrary フルスコープを廃止し、
        アルバムの読み取りに photoslibrary.readonly.appcreateddata を要求するように
        なったため。追加先は GOOGLE_PHOTOS_BATCH_ALBUM_ID で ID を直接
        与えること。ID 直指定の mediaItems.batchCreate は appendonly だけで通る。
        """
        if album_name is None:
            album_name = self.album_name

        creds = self.get_credentials()
        if not creds:
            return None

        try:
            service = build(
                "photoslibrary", "v1", credentials=creds, static_discovery=False
            )

            # 既存のアルバムを検索
            albums = service.albums().list().execute()
            for album in albums.get("albums", []):
                if album["title"] == album_name:
                    return album["id"]

            # 新しいアルバムを作成
            album_body = {"album": {"title": album_name}}

            created_album = service.albums().create(body=album_body).execute()
            return created_album["id"]

        except HttpError as e:
            logger.error(f"Album creation failed: {e}")
            return None

    def _retry_with_backoff(self, func, *args, **kwargs):
        """指数バックオフでリトライを実行."""
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except (HttpError, requests.RequestException) as e:
                if attempt == self.max_retries:
                    raise e

                # HTTP 429 (Rate Limit) や 500系エラーの場合のみリトライ
                if hasattr(e, "resp") and hasattr(e.resp, "status"):
                    if e.resp.status in [429, 500, 502, 503, 504]:
                        wait_time = self.retry_delay * (2**attempt)
                        logger.warning(
                            f"Retry attempt {attempt + 1}/{self.max_retries} after {wait_time}s due to HTTP {e.resp.status}"
                        )
                        time.sleep(wait_time)
                        continue
                elif isinstance(e, requests.RequestException):
                    wait_time = self.retry_delay * (2**attempt)
                    logger.warning(
                        f"Retry attempt {attempt + 1}/{self.max_retries} after {wait_time}s due to network error: {e}"
                    )
                    time.sleep(wait_time)
                    continue

                raise e
            except Exception as e:
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * (2**attempt)
                    logger.warning(
                        f"Retry attempt {attempt + 1}/{self.max_retries} after {wait_time}s due to error: {e}"
                    )
                    time.sleep(wait_time)
                    continue
                raise e

    def upload_photo(
        self, file_path: str, description: str = "", album_id: Optional[str] = None
    ) -> Optional[str]:
        """写真を Google Photos にアップロードし、メディアアイテムIDを返す."""
        creds = self.get_credentials()
        if not creds:
            raise ValueError("Not authenticated with Google Photos")

        try:
            return self._retry_with_backoff(
                self._upload_photo_impl, file_path, description, creds, album_id
            )
        except Exception as e:
            logger.error(f"Photo upload failed after {self.max_retries} retries: {e}")
            return None

    def _upload_photo_impl(
        self,
        file_path: str,
        description: str,
        creds: Credentials,
        album_id: Optional[str] = None,
    ) -> Optional[str]:
        """実際のアップロード処理."""
        service = build(
            "photoslibrary", "v1", credentials=creds, static_discovery=False
        )

        # Step 1: アップロードトークンを取得
        with open(file_path, "rb") as photo_file:
            photo_bytes = photo_file.read()

        upload_url = "https://photoslibrary.googleapis.com/v1/uploads"
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/octet-stream",
            "X-Goog-Upload-File-Name": Path(file_path).name,
            "X-Goog-Upload-Protocol": "raw",
        }

        upload_response = requests.post(
            upload_url, data=photo_bytes, headers=headers, timeout=30
        )

        if upload_response.status_code != 200:
            logger.error(
                f"Upload failed: {upload_response.status_code} - {upload_response.text}"
            )
            if upload_response.status_code in [429, 500, 502, 503, 504]:
                raise requests.RequestException(
                    f"HTTP {upload_response.status_code}: {upload_response.text}"
                )
            return None

        upload_token = upload_response.text

        # Step 2: メディアアイテムを作成
        if not album_id:
            album_id = self.batch_album_id or self.create_album()

        # Get current JST timestamp
        # Note: Timestamp is now set via EXIF data in the image

        create_body = {
            "newMediaItems": [
                {
                    "description": description,
                    "simpleMediaItem": {
                        "uploadToken": upload_token,
                        "fileName": Path(file_path).name,
                    },
                }
            ]
        }

        # Note: Google Photos API does not support setting creation time in batchCreate
        # The timestamp must be set in the EXIF data of the image before upload

        if album_id:
            create_body["albumId"] = album_id

        create_response = service.mediaItems().batchCreate(body=create_body).execute()

        if create_response.get("newMediaItemResults"):
            result = create_response["newMediaItemResults"][0]
            status = result.get("status", {})
            status_code = status.get("code")
            status_message = status.get("message")
            is_success = (
                status_code in (0, "OK") or (status_message or "").upper() == "SUCCESS"
            )
            if is_success:
                media_item_id = result["mediaItem"]["id"]
                logger.info(
                    f"Successfully uploaded photo to Google Photos: {media_item_id}"
                )
                return media_item_id
            else:
                logger.error(f"Media item creation failed: {status}")
                return None
        else:
            logger.error("No media item results returned")
            return None

    def upload_photo_from_url(
        self, photo_url: str, description: str = "", album_id: Optional[str] = None
    ) -> Optional[str]:
        """URLから写真をダウンロードしてGoogle Photosにアップロード."""
        temp_file_path = None
        try:
            # SSRF 対策: allowlist 済ホスト（GCS）以外は取得しない
            if not is_allowed_storage_url(photo_url):
                raise ValueError(
                    f"Refusing to fetch non-allowlisted photo URL: {photo_url}"
                )

            # URLから画像をダウンロード（リトライ機能付き）
            response = self._retry_with_backoff(
                requests.get, photo_url, timeout=30, allow_redirects=False
            )
            response.raise_for_status()

            # Content-Type の検証
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                raise ValueError(f"Invalid content type: {content_type}")

            # ファイルサイズの検証（最大100MB）
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > 100 * 1024 * 1024:
                raise ValueError(f"File too large: {content_length} bytes")

            # 一時ファイルに保存
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name

            logger.info(f"Downloaded photo from URL: {photo_url} -> {temp_file_path}")

            # Google Photos にアップロード
            result = self.upload_photo(temp_file_path, description, album_id=album_id)
            if result:
                logger.info(
                    f"Successfully uploaded photo from URL to Google Photos: {result}"
                )
            return result

        except Exception as e:
            logger.error(f"Photo upload from URL failed: {e}")
            return None
        finally:
            # 一時ファイルを削除
            if temp_file_path:
                try:
                    Path(temp_file_path).unlink(missing_ok=True)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}"
                    )

    def upload_file(
        self, local_path: str, remote_path: str, content_type: Optional[str] = None
    ) -> str:
        """ファイルを Google Photos にアップロード（制限付き実装）."""
        # Google Photos API は直接的なパス指定をサポートしないため、
        # 写真としてアップロードし、メディアアイテムIDを返す
        logger.warning(
            f"Google Photos does not support direct path uploads. Ignoring remote_path: {remote_path}"
        )
        result = self.upload_photo(local_path, description=remote_path)
        if result:
            return f"googlephotos://{result}"
        raise Exception("Failed to upload file to Google Photos")

    def upload_json(self, data: dict, remote_path: str) -> str:
        """JSON データのアップロード（Google Photos では非サポート）."""
        raise NotImplementedError("Google Photos does not support JSON file uploads")

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Google Photos からのダウンロード（制限付き）."""
        # Google Photos API は直接的なダウンロードを制限しているため、
        # 実装は限定的
        logger.warning("Google Photos API has limited download capabilities")
        return False

    def download_json(self, remote_path: str) -> Optional[dict]:
        """JSON データのダウンロード（Google Photos では非サポート）."""
        logger.warning("Google Photos does not support JSON file storage")
        return None

    def exists(self, remote_path: str) -> bool:
        """ファイルの存在確認（Google Photos では制限付き）."""
        # メディアアイテムIDとして解釈
        if remote_path.startswith("googlephotos://"):
            # 実際の存在確認はAPIコールが必要だが、ここでは簡易実装
            return True
        return False
