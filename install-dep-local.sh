#!/bin/bash

# Script to install dependencies for flo_ai, wavefront/server (using uv) and wavefront/client (using pnpm)

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Installing dependencies for all projects...${NC}\n"

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Install dependencies for flo_ai using uv
echo -e "${YELLOW}[1/3] Installing dependencies for flo_ai using uv...${NC}"
cd flo_ai
if command -v uv &> /dev/null; then
    uv sync
    echo -e "${GREEN}✓ flo_ai dependencies installed successfully${NC}\n"
else
    echo -e "${YELLOW}Warning: uv not found. Please install uv first.${NC}\n"
    exit 1
fi
cd ..

# 2. Install dependencies for wavefront/server using uv
echo -e "${YELLOW}[2/3] Installing dependencies for wavefront/server using uv...${NC}"
cd wavefront/server
if command -v uv &> /dev/null; then
    uv sync --all-packages
    echo -e "${GREEN}✓ wavefront/server dependencies installed successfully${NC}\n"
else
    echo -e "${YELLOW}Warning: uv not found. Please install uv first.${NC}\n"
    exit 1
fi
cd ../..

# 3. Install dependencies for wavefront/client using pnpm
echo -e "${YELLOW}[3/3] Installing dependencies for wavefront/client using pnpm...${NC}"
cd wavefront/client
if command -v pnpm &> /dev/null; then
    pnpm install
    echo -e "${GREEN}✓ wavefront/client dependencies installed successfully${NC}\n"
else
    echo -e "${YELLOW}Warning: pnpm not found. Please install pnpm first.${NC}\n"
    exit 1
fi
cd ../..

echo -e "${GREEN}All dependencies installed successfully!${NC}"
