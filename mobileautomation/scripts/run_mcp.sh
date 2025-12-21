#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_NAME="mobileautomation-mcp:latest"

cd "${PROJECT_ROOT}"

echo "Building ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" .

echo "Starting MCP server container (stdio)..."
exec docker run --rm -i \
  -v /var/run/docker.sock:/var/run/docker.sock \
  "${IMAGE_NAME}"

