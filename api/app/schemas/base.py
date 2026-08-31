"""Base schema configuration for API responses with automatic snake_case to camelCase conversion."""

from pydantic import BaseModel as PydanticBaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class BaseModel(PydanticBaseModel):
    """Base model with automatic snake_case to camelCase conversion for JSON serialization."""

    model_config = ConfigDict(
        # Convert snake_case field names to camelCase in JSON
        alias_generator=to_camel,
        # Use field values for serialization
        populate_by_name=True,
        # Validate on assignment
        validate_assignment=True,
        # Include original field names in schema
        json_schema_extra={
            "example": "Field names are automatically converted from snake_case to camelCase"
        },
    )
