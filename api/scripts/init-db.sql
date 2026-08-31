-- Database initialization script for PostgreSQL
-- Issue #40: Coordinate Recorder Database Setup

-- Set timezone to UTC
SET timezone = 'UTC';

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create indexes for performance optimization
-- Note: Tables will be created by SQLAlchemy, this script adds optimizations

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON DATABASE coordinate_db TO coordinate_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO coordinate_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO coordinate_user;

-- Set default permissions for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO coordinate_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO coordinate_user;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialization completed successfully';
END $$;
