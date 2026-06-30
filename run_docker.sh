#!/usr/bin/env bash
# ============================================================
# Run the FastAPI application in a Docker container
# ============================================================

set -euo pipefail

IMAGE_NAME="oauth_python_api"
PORT=8000
ENV_FILE=".env"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting Docker container for $IMAGE_NAME...${NC}"

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: $ENV_FILE not found!${NC}"
    echo -e "You must run the Azure setup scripts or copy .env.example to .env and configure it before running the container."
    exit 1
fi

# Build the image if it doesn't exist
if ! docker image inspect "$IMAGE_NAME" > /dev/null 2>&1; then
    echo -e "${YELLOW}Image '$IMAGE_NAME' not found. Building it now...${NC}"
    docker build -t "$IMAGE_NAME" .
fi

echo -e "${GREEN}Running container on http://localhost:$PORT${NC}"
echo -e "${YELLOW}(Press Ctrl+C to stop)${NC}"

# Run the container:
#  --rm: automatically clean up the container and remove it when it stops
#  -p 8000:8000: map localhost:8000 to container port 8000
#  --env-file .env: pass the Azure AD environment variables to the container
docker run --rm -p "$PORT:$PORT" --env-file "$ENV_FILE" "$IMAGE_NAME"
