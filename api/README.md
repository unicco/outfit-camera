# Coordinate Recorder Backend

Backend service for the smart wardrobe management system using FastAPI, Roboflow AI, and Google Cloud Storage.

## Architecture Improvements (Issue #715)

### Dependency Injection Pattern

The API now uses FastAPI's dependency injection system for service management:

- **Singleton Pattern**: ClothingExtractor, ImageUploadService, and JinaAPIService are implemented as singletons to reduce memory usage and improve performance
- **Configuration Management**: Settings are managed via Pydantic BaseModel with environment variable support
- **Testability**: Easy mock injection using FastAPI's `dependency_overrides`

For coding conventions, see [API Coding Standards](../docs/development/api-coding-standards.md).

## Features

- FastAPI-based REST API
- Roboflow AI clothing detection with GrabCut background removal
- PostgreSQL database with SQLAlchemy ORM
- Google Cloud Storage integration for wardrobe images
- Automatic daily outfit capture
- Real-time photo processing
- Jina AI embedding for wardrobe item matching

## API Endpoints

### Photos API

- `GET /api/v2/photos` - Get recent photos
- `GET /api/v2/records` - Get outfit records
- `GET /api/v2/daily-status` - Get daily capture status
- `POST /api/v2/photos/{photo_id}/capture` - Mark photo as captured
- `DELETE /api/v2/photos/no-person` - Delete photos without detected persons
- `GET /api/v2/stats` - Get system statistics

### Wardrobe Management API

#### Items Management

- `GET /api/v2/wardrobe/items` - List all clothing items
  - Query params: `category`, `status`
- `POST /api/v2/wardrobe/items` - Create new clothing item
- `GET /api/v2/wardrobe/items/{item_id}` - Get specific item
- `PUT /api/v2/wardrobe/items/{item_id}` - Update item
- `DELETE /api/v2/wardrobe/items/{item_id}` - Soft delete item

#### Image Upload

- `POST /api/v2/wardrobe/items/{item_id}/images` - Upload images for an item
  - Supports multiple file upload
  - Automatic thumbnail generation (200x200, 400x400)
  - Supported formats: JPEG, PNG, WebP

Example using curl:

```bash
curl -X POST "http://localhost:8000/api/v2/wardrobe/items/{item_id}/images" \
  -H "accept: application/json" \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg"
```

Response:

```json
{
  "item_id": "123e4567-e89b-12d3-a456-426614174000",
  "uploaded_images": [
    {
      "id": "file-123",
      "original_url": "https://storage.googleapis.com/bucket/wardrobe/item/file.jpg",
      "thumbnails": {
        "thumb_200": "https://storage.googleapis.com/bucket/wardrobe/item/file_thumb_200.jpg",
        "thumb_400": "https://storage.googleapis.com/bucket/wardrobe/item/file_thumb_400.jpg"
      },
      "size": 1048576,
      "content_type": "image/jpeg",
      "filename": "shirt.jpg"
    }
  ]
}
```

### Camera Integration

- `POST /upload` - Upload photo from camera service
- `GET /capture` - Trigger manual photo capture

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL 16+
- Google Cloud Storage account and credentials
- Poetry for dependency management

### Installation

1. Install dependencies:

```bash
poetry install
```

2. Set up environment variables:

```bash
# Create .env file with your configuration
touch .env
# Edit .env with required variables (see below)
```

3. Required environment variables:

```
DATABASE_URL=postgresql://user:pass@localhost:5432/coordinate_db
GCS_BUCKET_NAME=your-bucket-name
GCS_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

4. Run database migrations:

```bash
# データベースマイグレーション実行
cd api
alembic upgrade head
```

5. Start the server:

```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Development

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=app

# Run specific test file
poetry run pytest tests/test_wardrobe_api.py
poetry run pytest tests/test_image_upload_service.py
```

### Code Quality

```bash
# Format code
poetry run black app/ tests/

# Lint
poetry run ruff app/ tests/

# Type checking
poetry run mypy app/
```

## Environment Variables

See `.env.template` for all available configuration options.

## API Documentation

When running, API documentation is available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Wardrobe Data Model

### ClothingItem

- Basic info: name, category, subcategory, brand
- Colors: primary and secondary colors
- Properties: pattern, material, size
- Purchase info: date and price
- Usage: season, occasion tags
- Images: URLs and metadata stored in GCS

### Image Storage

- Original images stored in Google Cloud Storage
- Automatic thumbnail generation
- Public URLs for direct access
- Metadata tracking for all uploads
