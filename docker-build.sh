#!/bin/bash
# Build Docker image with git information embedded
# Usage: ./docker-build.sh [--no-cache]

set -e

# Get git information
export GIT_COMMIT_HASH=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
export GIT_COMMIT_SHORT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
export GIT_COMMIT_DATE=$(git log -1 --format=%cd --date=iso 2>/dev/null || echo "unknown")

# Check if working directory is dirty
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    export GIT_DIRTY="true"
else
    export GIT_DIRTY="false"
fi

echo "Building with git info:"
echo "  Commit: ${GIT_COMMIT_SHORT_HASH}"
echo "  Date: ${GIT_COMMIT_DATE}"
echo "  Dirty: ${GIT_DIRTY}"
echo ""

# Build using docker compose
docker compose build "$@"

echo ""
echo "Build complete. Run with: docker compose up -d"
