#!/bin/bash

# Environment Switcher for Coordinate Recorder
# Switches between test, development, and production environments

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_TYPE=${1:-development}

echo "🔄 Switching to $ENV_TYPE environment"

case $ENV_TYPE in
    test)
        if [ -f "$PROJECT_ROOT/.env.test" ]; then
            cp "$PROJECT_ROOT/.env.test" "$PROJECT_ROOT/.env"
            echo "✅ Test environment activated"
            echo "📊 Database: SQLite test database"
            echo "🔧 Debug mode: enabled"
        else
            echo "❌ .env.test not found"
            exit 1
        fi
        ;;
    development)
        if [ -f "$PROJECT_ROOT/.env.development" ]; then
            cp "$PROJECT_ROOT/.env.development" "$PROJECT_ROOT/.env"
            echo "✅ Development environment activated"
            echo "📊 Database: SQLite working database"
            echo "🌐 URLs: localhost"
        else
            echo "❌ .env.development not found"
            exit 1
        fi
        ;;
    production)
        if [ -f "$PROJECT_ROOT/.env.terraform" ]; then
            cp "$PROJECT_ROOT/.env.terraform" "$PROJECT_ROOT/.env"
            echo "✅ Production environment activated (Terraform managed)"
            echo "📊 Database: PostgreSQL production"
            echo "🌐 URLs: pi-camera.local"
        else
            echo "❌ .env.terraform not found"
            exit 1
        fi
        ;;
    *)
        echo "❌ Invalid environment: $ENV_TYPE"
        echo "Usage: $0 [test|development|production]"
        exit 1
        ;;
esac

echo "🎯 Environment switched to: $ENV_TYPE"
echo "📁 Active config: $PROJECT_ROOT/.env"
