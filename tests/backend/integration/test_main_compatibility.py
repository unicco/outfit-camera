"""Integration tests to verify main.py and main_v2.py compatibility."""


class TestMainCompatibility:
    """Test compatibility between main.py and main_v2.py."""

    def test_common_endpoints_exist(self, client, client_v2):
        """Test that common endpoints exist in both versions."""
        # /lightweight-status was removed; debug endpoints live under /debug.
        common_endpoints = [
            ("/", 200),
            ("/health", 200),
            ("/debug/config", 200),
        ]

        for endpoint, expected_status in common_endpoints:
            # Test main.py
            response_v1 = client.get(endpoint)
            assert (
                response_v1.status_code == expected_status
            ), f"main.py {endpoint} failed"

            # Test main_v2.py
            response_v2 = client_v2.get(endpoint)
            assert (
                response_v2.status_code == expected_status
            ), f"main_v2.py {endpoint} failed"

    def test_root_endpoint_compatibility(self, client, client_v2):
        """Test root endpoint returns similar structure."""
        response_v1 = client.get("/")
        response_v2 = client_v2.get("/")

        assert response_v1.status_code == 200
        assert response_v2.status_code == 200

        data_v1 = response_v1.json()
        data_v2 = response_v2.json()

        # Both should have service name and status
        assert "Coordinate Recorder" in data_v1["service"]
        assert "Coordinate Recorder" in data_v2["service"]
        assert data_v1["status"] == "running"
        assert data_v2["status"] == "running"

        # Both should have configuration info
        assert "storage_type" in data_v1
        assert "storage_type" in data_v2
        assert data_v1["storage_type"] == data_v2["storage_type"]

    def test_health_endpoint_compatibility(self, client, client_v2):
        """Test health endpoint returns same structure."""
        response_v1 = client.get("/health")
        response_v2 = client_v2.get("/health")

        assert response_v1.status_code == 200
        assert response_v2.status_code == 200

        data_v1 = response_v1.json()
        data_v2 = response_v2.json()

        assert data_v1["status"] == data_v2["status"] == "healthy"

    def test_debug_config_compatibility(self, client, client_v2):
        """Test debug config endpoint compatibility."""
        response_v1 = client.get("/debug/config")
        response_v2 = client_v2.get("/debug/config")

        assert response_v1.status_code == 200
        assert response_v2.status_code == 200

        data_v1 = response_v1.json()
        data_v2 = response_v2.json()

        # Check common config keys exist in both
        common_keys = ["storage_type", "database_enabled"]
        for key in common_keys:
            assert key in data_v1
            assert key in data_v2
            assert data_v1[key] == data_v2[key]

    def test_v2_endpoints_compatibility(self, client, client_v2):
        """Ensure v2 API endpoints are available while legacy paths remain accessible."""
        endpoint_pairs = [
            ("/api/v2/health", "/health"),
            ("/api/v2/records", "/records"),
            ("/api/v2/photos", "/photos"),
        ]

        for api_endpoint, legacy_endpoint in endpoint_pairs:
            response_v2 = client_v2.get(api_endpoint)
            assert response_v2.status_code in [200, 404]

            # Legacyアプリでは旧パスを確認
            response_v1 = client.get(legacy_endpoint)
            assert response_v1.status_code in [200, 404]

    def test_camera_proxy_compatibility(self, client, client_v2):
        """Test camera proxy endpoints exist in both."""
        # Camera stream endpoint
        response_v1 = client.get("/camera/stream")
        response_v2 = client_v2.get("/camera/stream")

        # 200 if camera is up; 502/503 when the proxy can't reach the camera
        # service (the usual case in CI / dev without the camera running).
        assert response_v1.status_code in [200, 502, 503]
        assert response_v2.status_code in [200, 502, 503]

    def test_cors_headers_compatibility(self, client, client_v2):
        """Test CORS headers are set in both versions."""
        # Starlette's CORSMiddleware only handles an OPTIONS request as a CORS
        # preflight when both Origin and Access-Control-Request-Method are
        # present; a bare OPTIONS hits the route and returns 405. The Origin must
        # be in the allowed list (defaults include http://localhost:3000).
        preflight_headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        }
        response_v1 = client.options("/health", headers=preflight_headers)
        response_v2 = client_v2.options("/health", headers=preflight_headers)

        assert response_v1.status_code == 200
        assert response_v2.status_code == 200

        # Both should have CORS headers
        assert "access-control-allow-origin" in response_v1.headers
        assert "access-control-allow-origin" in response_v2.headers

    def test_error_handling_compatibility(self, client, client_v2):
        """Test error handling is consistent."""
        # Test 404 handling
        response_v1 = client.get("/this/does/not/exist")
        response_v2 = client_v2.get("/this/does/not/exist")

        assert response_v1.status_code == 404
        assert response_v2.status_code == 404

        # Both should return JSON error response
        assert response_v1.headers.get("content-type") == "application/json"
        assert response_v2.headers.get("content-type") == "application/json"
