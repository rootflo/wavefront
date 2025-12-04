#!/bin/bash

# Simple Image Search Test Script (No Authentication)

set -e  # Exit on any error

# Configuration
BASE_URL="http://0.0.0.0:8001"
IMAGE_FILE="query.png"
IKB_ID="fc562847-e2cf-4f6e-bd1e-708a7a3be8f8"  # Replace with your IKB ID

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Image Search Test (No Auth) ===${NC}"
echo "Base URL: $BASE_URL"
echo "Image File: $IMAGE_FILE"
echo ""

# Step 1: Check if image file exists
if [ ! -f "$IMAGE_FILE" ]; then
    echo -e "${RED}Error: Image file '$IMAGE_FILE' not found${NC}"
    echo "Available files in test_images directory:"
    ls -la "modules/image_search_module/tests/test_images/" 2>/dev/null || echo "Directory not found"
    exit 1
fi

echo -e "${GREEN}✓ Image file found${NC}"
echo ""

# Step 2: Prepare image data
echo -e "${YELLOW}Step 1: Preparing image data...${NC}"
base64 -i "$IMAGE_FILE" | tr -d '\n' > /tmp/image_base64.txt
echo -e "${GREEN}✓ Image converted to base64 ($(wc -c < /tmp/image_base64.txt) characters)${NC}"
echo ""

# Step 3: Add image to IKB
echo -e "${YELLOW}Step 2: Adding image to IKB...${NC}"

# Create request payload for adding image
cat > /tmp/add_payload.json << EOF
{
  "image_data": "data:image/png;base64,$(cat /tmp/image_base64.txt)",
  "reference_id": "test_reference_$(date +%s)",
  "metadata": {
    "description": "Test image for no-auth script",
    "category": "test",
    "source": "no_auth_test",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  }
}
EOF

echo "Request payload size: $(wc -c < /tmp/add_payload.json) characters"

ADD_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d @/tmp/add_payload.json \
    "$BASE_URL/floware/ikb/$IKB_ID/add")

echo "Add Image Response: $ADD_RESPONSE"
echo ""

# Check if add was successful
ADD_STATUS=$(echo "$ADD_RESPONSE" | jq -r '.meta.status // "unknown"')
if [ "$ADD_STATUS" = "success" ]; then
    echo -e "${GREEN}✓ Successfully added image to IKB${NC}"

    # Extract reference ID for verification
    REFERENCE_ID=$(echo "$ADD_RESPONSE" | jq -r '.data.reference_id // "unknown"')
    echo "Reference ID: $REFERENCE_ID"
else
    echo -e "${RED}✗ Failed to add image to IKB${NC}"
    echo "Error: $(echo "$ADD_RESPONSE" | jq -r '.meta.error // "Unknown error"')"
    # Continue to search anyway to test the search endpoint
fi

echo ""

# Step 4: Search for the same image
echo -e "${YELLOW}Step 3: Searching for the same image...${NC}"

# Create search payload
cat > /tmp/search_payload.json << EOF
{
  "image_data": "data:image/png;base64,$(cat /tmp/image_base64.txt)",
  "max_results": 5,
  "threshold": 0.7
}
EOF

echo "Search payload size: $(wc -c < /tmp/search_payload.json) characters"

SEARCH_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -d @/tmp/search_payload.json \
    "$BASE_URL/floware/ikb/$IKB_ID/search")

echo "Search Response: $SEARCH_RESPONSE"
echo ""

# Check search results
SEARCH_STATUS=$(echo "$SEARCH_RESPONSE" | jq -r '.meta.status // "unknown"')
if [ "$SEARCH_STATUS" = "success" ]; then
    echo -e "${GREEN}✓ Search completed successfully${NC}"

    # Extract and display match count
    MATCH_COUNT=$(echo "$SEARCH_RESPONSE" | jq -r '.data.matches | length // 0')
    echo "Number of matches found: $MATCH_COUNT"

    if [ "$MATCH_COUNT" -gt 0 ]; then
        echo -e "${GREEN}✓ Found matching images!${NC}"

        # Display match details
        echo "Match details:"
        echo "$SEARCH_RESPONSE" | jq '.data.matches[] | {reference_id: .reference_id, match_score: .match_score, confidence: .confidence, is_match: .is_match}'

        # Check if our added image is in the results
        if [ -n "$REFERENCE_ID" ] && [ "$REFERENCE_ID" != "unknown" ]; then
            FOUND_OUR_IMAGE=$(echo "$SEARCH_RESPONSE" | jq -r --arg ref_id "$REFERENCE_ID" '.data.matches[] | select(.reference_id == $ref_id) | .reference_id // empty')
            if [ -n "$FOUND_OUR_IMAGE" ]; then
                echo -e "${GREEN}✓ Our added image was found in search results!${NC}"
            else
                echo -e "${YELLOW}⚠ Our added image was not found in search results${NC}"
            fi
        fi
    else
        echo -e "${YELLOW}⚠ No matches found${NC}"
    fi
else
    echo -e "${RED}✗ Search failed${NC}"
    echo "Error: $(echo "$SEARCH_RESPONSE" | jq -r '.meta.error // "Unknown error"')"
fi

echo ""

# Step 5: Test IKB info endpoint
echo -e "${YELLOW}Step 4: Testing IKB info endpoint...${NC}"
IKB_INFO_RESPONSE=$(curl -s -X GET "$BASE_URL/floware/ikb/$IKB_ID")
echo "IKB Info Response: $IKB_INFO_RESPONSE"

# Clean up temporary files
rm -f /tmp/image_base64.txt /tmp/add_payload.json /tmp/search_payload.json

echo ""
echo -e "${BLUE}=== Test Complete ===${NC}"
