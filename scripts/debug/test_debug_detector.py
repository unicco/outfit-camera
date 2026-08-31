#!/usr/bin/env python3
"""Test debug detector endpoint."""

import json
import os
from urllib.parse import urljoin

import requests


def _get_base_url() -> str:
    """Return API base URL, falling back to localhost."""
    return os.environ.get("API_URL", "http://localhost:8000")


def main() -> None:
    base_url = _get_base_url().rstrip("/") + "/"
    endpoint = urljoin(base_url, "api/v2/ai/debug-detector")
    response = requests.get(endpoint, timeout=10)

    print("Status Code:", response.status_code)
    print("\nResponse:")
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
