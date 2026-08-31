#!/bin/bash
set -e

# Google Cloud Storage Setup Script for Coordinate Recorder
# This script automates the GCS setup process

echo "🚀 Google Cloud Storage Setup for Coordinate Recorder"
echo "====================================================="

# Check prerequisites
command -v gcloud >/dev/null 2>&1 || { echo "❌ gcloud CLI is required but not installed."; exit 1; }
command -v gsutil >/dev/null 2>&1 || { echo "❌ gsutil is required but not installed."; exit 1; }

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Prompt for configuration
read -p "Enter your GCP Project ID: " PROJECT_ID
read -p "Enter environment (dev/prod): " ENVIRONMENT

# Set bucket name based on environment
if [ "$ENVIRONMENT" = "prod" ]; then
    BUCKET_NAME="coordinate-recorder-photos-prod"
else
    BUCKET_NAME="coordinate-recorder-photos-dev"
fi

REGION="asia-northeast1"
SERVICE_ACCOUNT_NAME="coordinate-recorder-gcs"

echo ""
echo "Configuration:"
echo "  Project ID: $PROJECT_ID"
echo "  Environment: $ENVIRONMENT"
echo "  Bucket Name: $BUCKET_NAME"
echo "  Region: $REGION"
echo ""

read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Setup cancelled."
    exit 0
fi

# Set project
echo "Setting GCP project..."
gcloud config set project $PROJECT_ID

# Create service account
echo ""
echo "Creating service account..."
if gcloud iam service-accounts describe $SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com >/dev/null 2>&1; then
    echo "Service account already exists."
else
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --description="Service account for Coordinate Recorder GCS access" \
        --display-name="Coordinate Recorder GCS"
    echo "Service account created."
fi

# Grant permissions
echo ""
echo "Granting permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin" --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.legacyBucketReader" --quiet

# Create service account key
echo ""
echo "Creating service account key..."
mkdir -p ./secrets
chmod 700 ./secrets

if [ -f "./secrets/gcs-service-account-key.json" ]; then
    echo "⚠️  Service account key already exists. Skipping creation."
else
    gcloud iam service-accounts keys create ./secrets/gcs-service-account-key.json \
        --iam-account=$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com
    chmod 600 ./secrets/gcs-service-account-key.json
    echo "Service account key created."
fi

# Create bucket
echo ""
echo "Creating GCS bucket..."
if gsutil ls -b gs://$BUCKET_NAME >/dev/null 2>&1; then
    echo "Bucket already exists."
else
    gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://$BUCKET_NAME/
    echo "Bucket created."
fi

# Create folder structure
echo ""
echo "Creating folder structure..."
touch .placeholder
gsutil cp .placeholder gs://$BUCKET_NAME/photos/.placeholder
gsutil cp .placeholder gs://$BUCKET_NAME/thumbnails/.placeholder
gsutil cp .placeholder gs://$BUCKET_NAME/temp/.placeholder
rm .placeholder

# Apply CORS configuration
echo ""
echo "Applying CORS configuration..."
cat > cors-config.json << EOF
[
  {
    "origin": ["http://localhost:3000", "http://localhost:3001", "http://pi-camera.local:3000"],
    "method": ["GET", "HEAD", "PUT", "POST", "DELETE"],
    "responseHeader": ["Content-Type", "Access-Control-Allow-Origin", "x-goog-content-length-range"],
    "maxAgeSeconds": 3600
  }
]
EOF
gsutil cors set cors-config.json gs://$BUCKET_NAME
rm cors-config.json

# Apply lifecycle configuration
echo ""
echo "Applying lifecycle configuration..."
cat > lifecycle-config.json << EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 7, "matchesPrefix": ["temp/"]}
      },
      {
        "action": {"type": "Delete"},
        "condition": {"age": 90, "matchesPrefix": ["thumbnails/"]}
      }
    ]
  }
}
EOF
gsutil lifecycle set lifecycle-config.json gs://$BUCKET_NAME
rm lifecycle-config.json

# Grant service account access to bucket
echo ""
echo "Granting bucket access..."
gsutil iam ch serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com:objectAdmin gs://$BUCKET_NAME

# Create/update .env file
echo ""
echo "Updating .env configuration..."
if [ ! -f .env ]; then
    cp .env.template .env
fi

# Update .env with GCS settings
if grep -q "GCS_PROJECT_ID" .env; then
    sed -i.bak "s/GCS_PROJECT_ID=.*/GCS_PROJECT_ID=$PROJECT_ID/" .env
else
    echo "GCS_PROJECT_ID=$PROJECT_ID" >> .env
fi

if grep -q "GCS_BUCKET_NAME" .env; then
    sed -i.bak "s/GCS_BUCKET_NAME=.*/GCS_BUCKET_NAME=$BUCKET_NAME/" .env
else
    echo "GCS_BUCKET_NAME=$BUCKET_NAME" >> .env
fi

if grep -q "STORAGE_TYPE" .env; then
    sed -i.bak "s/STORAGE_TYPE=.*/STORAGE_TYPE=gcs/" .env
else
    echo "STORAGE_TYPE=gcs" >> .env
fi

# Test configuration
echo ""
echo "Testing configuration..."
export GOOGLE_APPLICATION_CREDENTIALS="./secrets/gcs-service-account-key.json"
echo "test" > test.txt
if gsutil cp test.txt gs://$BUCKET_NAME/temp/test.txt; then
    echo "✅ Upload test successful"
    gsutil rm gs://$BUCKET_NAME/temp/test.txt
else
    echo "❌ Upload test failed"
fi
rm test.txt

# Summary
echo ""
echo "✅ GCS Setup Complete!"
echo "====================="
echo ""
echo "Next steps:"
echo "1. Review the generated configuration in .env"
echo "2. Ensure .gitignore includes 'secrets/' directory"
echo "3. Restart services to apply changes:"
echo "   ./scripts/start-development.sh"
echo ""
echo "Documentation:"
echo "- Service Account Setup: docs/GCS_SERVICE_ACCOUNT_SETUP.md"
echo "- Bucket Configuration: docs/GCS_BUCKET_CONFIGURATION.md"
echo "- Security Best Practices: docs/GCS_SECURITY_BEST_PRACTICES.md"
