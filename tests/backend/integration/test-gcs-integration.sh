#!/bin/bash
set -e

# Test script for Google Cloud Storage integration
# This script verifies that GCS is properly configured and working

echo "🧪 Testing Google Cloud Storage Integration"
echo "=========================================="

echo "Running GCS integration tests"

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check required environment variables
echo ""
echo "1. Checking environment variables..."
REQUIRED_VARS="GCS_PROJECT_ID GCS_BUCKET_NAME GOOGLE_APPLICATION_CREDENTIALS"
for var in $REQUIRED_VARS; do
    if [ -z "${!var}" ]; then
        echo "❌ Missing: $var"
        exit 1
    else
        echo "✅ Found: $var = ${!var}"
    fi
done

# Check service account key file
echo ""
echo "2. Checking service account key..."
if [ -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "✅ Key file exists: $GOOGLE_APPLICATION_CREDENTIALS"
    # Check if it's valid JSON
    if python3 -m json.tool "$GOOGLE_APPLICATION_CREDENTIALS" > /dev/null 2>&1; then
        echo "✅ Key file is valid JSON"
    else
        echo "❌ Key file is not valid JSON"
        exit 1
    fi
else
    echo "❌ Key file not found: $GOOGLE_APPLICATION_CREDENTIALS"
    exit 1
fi

# Test Python GCS client
echo ""
echo "3. Testing Python GCS client..."
python3 << EOF
import sys
try:
    from google.cloud import storage
    print("✅ google-cloud-storage module imported successfully")

    # Create client
    client = storage.Client()
    print(f"✅ GCS client created for project: {client.project}")

    # Test bucket access
    bucket_name = "$GCS_BUCKET_NAME"
    try:
        bucket = client.bucket(bucket_name)
        # Try to list one object instead of bucket.reload()
        list(bucket.list_blobs(max_results=1))
        print(f"✅ Bucket accessible: {bucket_name}")
    except Exception as e:
        print(f"❌ Cannot access bucket: {e}")
        sys.exit(1)

except ImportError:
    print("❌ google-cloud-storage module not installed")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
EOF

# Test file operations
echo ""
echo "4. Testing file operations..."

# Create test file
TEST_FILE="test_$(date +%s).txt"
TEST_CONTENT="GCS integration test at $(date)"
echo "$TEST_CONTENT" > /tmp/$TEST_FILE

# Upload test
echo "   Uploading test file..."
python3 << EOF
from google.cloud import storage
import sys

try:
    client = storage.Client()
    bucket = client.bucket("$GCS_BUCKET_NAME")
    blob = bucket.blob("temp/$TEST_FILE")
    blob.upload_from_filename("/tmp/$TEST_FILE")
    print("   ✅ Upload successful")
except Exception as e:
    print(f"   ❌ Upload failed: {e}")
    sys.exit(1)
EOF

# Download test
echo "   Downloading test file..."
python3 << EOF
from google.cloud import storage
import sys

try:
    client = storage.Client()
    bucket = client.bucket("$GCS_BUCKET_NAME")
    blob = bucket.blob("temp/$TEST_FILE")
    blob.download_to_filename("/tmp/${TEST_FILE}.downloaded")

    # Verify content
    with open("/tmp/${TEST_FILE}.downloaded", 'r') as f:
        content = f.read().strip()

    if content == "$TEST_CONTENT":
        print("   ✅ Download successful and content verified")
    else:
        print("   ❌ Downloaded content doesn't match")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Download failed: {e}")
    sys.exit(1)
EOF

# List files test
echo "   Listing files in temp/ folder..."
python3 << EOF
from google.cloud import storage
import sys

try:
    client = storage.Client()
    bucket = client.bucket("$GCS_BUCKET_NAME")
    blobs = list(bucket.list_blobs(prefix="temp/"))
    print(f"   ✅ Found {len(blobs)} files in temp/")
    for blob in blobs[:5]:  # Show first 5
        print(f"      - {blob.name}")
except Exception as e:
    print(f"   ❌ List failed: {e}")
    sys.exit(1)
EOF

# Delete test file
echo "   Cleaning up test file..."
python3 << EOF
from google.cloud import storage
import sys

try:
    client = storage.Client()
    bucket = client.bucket("$GCS_BUCKET_NAME")
    blob = bucket.blob("temp/$TEST_FILE")
    blob.delete()
    print("   ✅ Cleanup successful")
except Exception as e:
    print(f"   ❌ Cleanup failed: {e}")
    # Don't exit on cleanup failure
EOF

# Clean up local files
rm -f /tmp/$TEST_FILE /tmp/${TEST_FILE}.downloaded

# Test signed URL generation
echo ""
echo "5. Testing signed URL generation..."
python3 << EOF
from google.cloud import storage
import datetime
import sys

try:
    client = storage.Client()
    bucket = client.bucket("$GCS_BUCKET_NAME")
    blob = bucket.blob("test/signed_url_test.txt")

    # Generate signed URL
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=15),
        method="GET"
    )

    if url and url.startswith("https://"):
        print("   ✅ Signed URL generated successfully")
        print(f"      URL length: {len(url)} characters")
    else:
        print("   ❌ Invalid signed URL generated")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Signed URL generation failed: {e}")
    sys.exit(1)
EOF

# Summary
echo ""
echo "========================================"
echo "✅ All GCS integration tests passed!"
echo ""
echo "Your GCS configuration is working correctly."
echo "The application can now use Google Cloud Storage for photo storage."
