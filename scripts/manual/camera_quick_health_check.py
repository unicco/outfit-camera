#!/usr/bin/env python3
"""Quick health test for camera service."""

import requests
import json


def test_health():
    try:
        response = requests.get("http://localhost:8001/health", timeout=5)
        print(f"Health Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Health Response: {json.dumps(data, indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Health Test Error: {e}")
        return False


def test_stream():
    try:
        response = requests.get("http://localhost:8001/stream", timeout=5, stream=True)
        print(f"Stream Status: {response.status_code}")
        print(f"Stream Content-Type: {response.headers.get('content-type', 'N/A')}")
        return response.status_code == 200
    except Exception as e:
        print(f"Stream Test Error: {e}")
        return False


if __name__ == "__main__":
    print("=== Quick Camera Service Test ===")
    health_ok = test_health()
    stream_ok = test_stream()

    print("\nResults:")
    print(f"Health: {'✅' if health_ok else '❌'}")
    print(f"Stream: {'✅' if stream_ok else '❌'}")
