"""Unit tests for API versioning functionality."""


class TestAPIVersioning:
    """Test API versioning functionality."""

    def test_supported_versions(self, client_v2):
        """`/api/versions` は v2 のみを公開する."""
        response = client_v2.get("/api/versions")
        assert response.status_code == 200

        data = response.json()
        assert data["default_version"] == "v2"
        assert data["latest_version"] == "v2"
        assert data["supported_versions"] == ["v2"]
        assert len(data["versions"]) == 1
        assert data["versions"][0]["base_path"] == "/api/v2"

    def test_api_root_endpoint(self, client_v2):
        """`/api` はガイダンスを返す."""
        response = client_v2.get("/api", follow_redirects=False)
        assert response.status_code == 200

        data = response.json()
        assert data["default_version"] == "v2"
        assert data["versions_endpoint"] == "/api/versions"

    def test_deprecated_path_returns_not_found(self, client_v2):
        """レガシーパスは 404 と移行メッセージを返す."""
        response = client_v2.get("/api/photos", follow_redirects=False)
        assert response.status_code == 404

        payload = response.json()
        assert payload["requested_path"] == "/api/photos"
        assert "/api/v2" in payload["message"]

    def test_versioned_path_passthrough(self, client_v2):
        """`/api/v2/...` は通常どおり処理される."""
        response = client_v2.get("/api/v2/health")
        assert response.status_code == 200

    def test_unknown_version(self, client_v2):
        """未サポートのバージョンは 404 を返す."""
        response = client_v2.get("/api/v3/status", follow_redirects=False)
        assert response.status_code == 404
        assert response.json()["message"].startswith("This endpoint has been retired")
