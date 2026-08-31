#!/usr/bin/env python3
"""Manual GCS setup script using Python SDK
Run this if gcloud CLI is not available.
"""

import os
import sys

from google.api_core import exceptions
from google.cloud import storage


def main():
    print("🚀 Google Cloud Storage Setup (Python SDK)")
    print("=========================================")

    # Check environment
    project_id = os.getenv("GCS_PROJECT_ID")
    bucket_name = os.getenv("GCS_BUCKET_NAME")

    if not project_id or not bucket_name:
        print("❌ Please set GCS_PROJECT_ID and GCS_BUCKET_NAME in .env")
        sys.exit(1)

    print(f"📋 Project ID: {project_id}")
    print(f"📋 Bucket Name: {bucket_name}")

    # Create storage client
    try:
        client = storage.Client(project=project_id)
        print("✅ Successfully authenticated with GCS")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        sys.exit(1)

    # Create bucket
    print(f"\n1. Creating bucket '{bucket_name}'...")
    try:
        bucket = client.bucket(bucket_name)
        bucket.location = "ASIA-NORTHEAST1"  # Tokyo region
        bucket.storage_class = "STANDARD"
        bucket = client.create_bucket(bucket)
        print(f"✅ Bucket created: {bucket.name}")
    except exceptions.Conflict:
        print(f"⚠️  Bucket already exists: {bucket_name}")
        bucket = client.bucket(bucket_name)
    except Exception as e:
        print(f"❌ Failed to create bucket: {e}")
        sys.exit(1)

    # Set CORS configuration
    print("\n2. Setting CORS configuration...")
    cors_config = [
        {
            "origin": [
                "http://localhost:3000",
                "http://localhost:3001",
                "http://pi-camera.local:3000",
                "https://coordinate-recorder.com",
            ],
            "method": ["GET", "PUT", "POST", "DELETE"],
            "responseHeader": ["Content-Type", "x-goog-acl"],
            "maxAgeSeconds": 3600,
        }
    ]

    bucket.cors = cors_config
    bucket.patch()
    print("✅ CORS configuration applied")

    # Set lifecycle rules
    print("\n3. Setting lifecycle rules...")
    lifecycle_rules = [
        {
            "action": {"type": "Delete"},
            "condition": {"age": 7, "matchesPrefix": ["temp/"]},
        },
        {
            "action": {"type": "Delete"},
            "condition": {"age": 90, "matchesPrefix": ["thumbnails/"]},
        },
    ]

    bucket.lifecycle_rules = lifecycle_rules
    bucket.patch()
    print("✅ Lifecycle rules applied")

    # Create test folders
    print("\n4. Creating folder structure...")
    folders = ["photos/", "thumbnails/", "temp/", "wardrobe/"]
    for folder in folders:
        blob = bucket.blob(folder)
        blob.upload_from_string("")
        print(f"   ✅ Created: {folder}")

    # Test write access
    print("\n5. Testing write access...")
    test_blob = bucket.blob("temp/test.txt")
    test_blob.upload_from_string("GCS integration test")
    print("✅ Write test successful")

    # Generate public URL format
    print("\n✨ Setup Complete!")
    print(f"\nPublic URL format: https://storage.googleapis.com/{bucket_name}/{{path}}")
    print(
        f"Example: https://storage.googleapis.com/{bucket_name}/photos/2025/01/01/uuid.jpg"
    )

    print("\n📝 Next steps:")
    print("1. Run: ./scripts/test-gcs-integration.sh")
    print("2. Start services: ./scripts/start-development.sh")
    print("3. Test upload in the web interface")


if __name__ == "__main__":
    main()
