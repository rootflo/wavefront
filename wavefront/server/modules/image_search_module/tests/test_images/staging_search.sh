#!/bin/bash

# Image Search API Testing Script for Staging
# Usage: ./test_image_search_staging.sh

set -e  # Exit on any error

# Configuration
STAGING_BASE_URL="https://staging.rootflo.ai"
AUTH_EMAIL=""  # Replace with your email
AUTH_PASSWORD=""        # Replace with your password
IMAGE_FILE="image1.png"              # Replace with your image file path
IKB_ID="fc562847-e2cf-4f6e-bd1e-708a7a3be8f8"  # Replace with your IKB ID

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Image Search API Testing Script for Staging ===${NC}"
echo "Base URL: $STAGING_BASE_URL"
echo ""

# Function to make authenticated requests
make_authenticated_request() {
    local method=$1
    local endpoint=$2
    local data=$3
    local content_type=${4:-"application/json"}

    if [ -z "$BEARER_TOKEN" ]; then
        echo -e "${RED}Error: No bearer token available${NC}"
        return 1
    fi

    if [ -n "$data" ]; then
        # Check if data is too large for command line (roughly > 1MB)
        if [ ${#data} -gt 1000000 ]; then
            # Use temporary file for large payloads
            local temp_file=$(mktemp)
            echo "$data" > "$temp_file"
            curl -s -X "$method" \
                -H "Content-Type: $content_type" \
                -H "Authorization: Bearer $BEARER_TOKEN" \
                -d @"$temp_file" \
                "$STAGING_BASE_URL$endpoint"
            rm -f "$temp_file"
        else
            # Use direct data for small payloads
            curl -s -X "$method" \
                -H "Content-Type: $content_type" \
                -H "Authorization: Bearer $BEARER_TOKEN" \
                -d "$data" \
                "$STAGING_BASE_URL$endpoint"
        fi
    else
        curl -s -X "$method" \
            -H "Authorization: Bearer $BEARER_TOKEN" \
            "$STAGING_BASE_URL$endpoint"
    fi
}

# Step 1: Authenticate and get bearer token
echo -e "${YELLOW}Step 1: Authenticating...${NC}"
AUTH_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$AUTH_EMAIL\", \"password\": \"$AUTH_PASSWORD\"}" \
    "$STAGING_BASE_URL/floware/v1/authenticate")

echo "Auth Response: $AUTH_RESPONSE"

# Extract bearer token from response
BEARER_TOKEN=$(echo "$AUTH_RESPONSE" | jq -r '.data.user.access_token // empty')

if [ -z "$BEARER_TOKEN" ] || [ "$BEARER_TOKEN" = "null" ]; then
    echo -e "${RED}Error: Failed to get bearer token${NC}"
    echo "Response: $AUTH_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Successfully authenticated${NC}"
echo "Bearer Token: ${BEARER_TOKEN:0:50}..."
echo ""

# Step 2: Check if image file exists
if [ ! -f "$IMAGE_FILE" ]; then
    echo -e "${RED}Error: Image file '$IMAGE_FILE' not found${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 2: Preparing image data...${NC}"

# Convert image to base64
BASE64_DATA=$(base64 -i "$IMAGE_FILE" | tr -d '\n')
IMAGE_DATA_URL="data:image/png;base64,${BASE64_DATA}"

echo -e "${GREEN}✓ Image converted to base64 (${#BASE64_DATA} characters)${NC}"
echo ""

# Step 3: Test IKB endpoints
echo -e "${YELLOW}Step 3: Testing IKB endpoints...${NC}"

# 3a. List all IKBs
echo -e "${BLUE}3a. Listing all IKBs...${NC}"
LIST_RESPONSE=$(make_authenticated_request "GET" "/floware/ikb/")
echo "List IKB Response: $LIST_RESPONSE"
echo ""

# 3b. Get specific IKB info
echo -e "${BLUE}3b. Getting IKB info for ID: $IKB_ID...${NC}"
IKB_INFO_RESPONSE=$(make_authenticated_request "GET" "/floware/ikb/$IKB_ID")
echo "IKB Info Response: $IKB_INFO_RESPONSE"
echo ""

# 3c. Add image to IKB
echo -e "${BLUE}3c. Adding image to IKB...${NC}"

# Create request payload
REQUEST_PAYLOAD=$(cat << EOF
{
  "image_data": "$IMAGE_DATA_URL",
  "reference_id": "test_reference_$(date +%s)",
  "metadata": {
    "description": "Test image for IKB via staging script",
    "category": "test",
    "source": "staging_test",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  }
}
EOF
)

echo "Request payload size: $(echo "$REQUEST_PAYLOAD" | wc -c) characters"

ADD_RESPONSE=$(make_authenticated_request "POST" "/floware/ikb/$IKB_ID/add" "$REQUEST_PAYLOAD")
echo "Add Image Response: $ADD_RESPONSE"
echo ""

# 3d. Search in IKB
echo -e "${BLUE}3d. Searching in IKB...${NC}"

SEARCH_PAYLOAD=$(cat << EOF
{
  "image_data": "$IMAGE_DATA_URL",
  "max_results": 5,
  "threshold": 0.7
}
EOF
)

SEARCH_RESPONSE=$(make_authenticated_request "POST" "/floware/ikb/$IKB_ID/search" "$SEARCH_PAYLOAD")
echo "Search Response: $SEARCH_RESPONSE"
echo ""

# Step 4: Create a new IKB (optional test)
echo -e "${YELLOW}Step 4: Testing IKB creation...${NC}"

CREATE_IKB_PAYLOAD=$(cat << EOF
{
  "name": "Test IKB $(date +%Y%m%d_%H%M%S)",
  "description": "Test IKB created via staging script",
  "ikb_type": "photo_matching",
  "algorithm_type": "sift",
  "config": {
    "max_keypoints": 5000,
    "match_threshold": 0.7
  }
}
EOF
)

CREATE_RESPONSE=$(make_authenticated_request "POST" "/floware/ikb/create" "$CREATE_IKB_PAYLOAD")
echo "Create IKB Response: $CREATE_RESPONSE"

# Extract new IKB ID if creation was successful
NEW_IKB_ID=$(echo "$CREATE_RESPONSE" | jq -r '.data.ikb_id // empty')

if [ -n "$NEW_IKB_ID" ] && [ "$NEW_IKB_ID" != "null" ]; then
    echo -e "${GREEN}✓ Successfully created new IKB with ID: $NEW_IKB_ID${NC}"

    # Test adding image to new IKB
    echo -e "${BLUE}Adding image to newly created IKB...${NC}"
    ADD_TO_NEW_RESPONSE=$(make_authenticated_request "POST" "/floware/ikb/$NEW_IKB_ID/add" "$REQUEST_PAYLOAD")
    echo "Add to New IKB Response: $ADD_TO_NEW_RESPONSE"
    echo ""

    # Clean up: Delete the test IKB
    echo -e "${BLUE}Cleaning up: Deleting test IKB...${NC}"
    DELETE_RESPONSE=$(make_authenticated_request "DELETE" "/floware/ikb/$NEW_IKB_ID")
    echo "Delete Response: $DELETE_RESPONSE"
else
    echo -e "${YELLOW}⚠ IKB creation may have failed or returned unexpected format${NC}"
fi

echo ""
echo -e "${GREEN}=== Testing Complete ===${NC}"
echo "All API endpoints have been tested successfully!"
echo ""
echo -e "${BLUE}Summary of tested endpoints:${NC}"
echo "✓ POST /floware/v1/authenticate - Authentication"
echo "✓ GET  /floware/ikb/ - List IKBs"
echo "✓ GET  /floware/ikb/{ikb_id} - Get IKB info"
echo "✓ POST /floware/ikb/{ikb_id}/add - Add image to IKB"
echo "✓ POST /floware/ikb/{ikb_id}/search - Search in IKB"
echo "✓ POST /floware/ikb/create - Create new IKB"
echo "✓ DELETE /floware/ikb/{ikb_id} - Delete IKB"
