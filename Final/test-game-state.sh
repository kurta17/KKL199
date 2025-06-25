#!/bin/bash
# test-game-state.sh
# Test game state synchronization between browsers

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== CHESS GAME STATE SYNCHRONIZATION TEST ===${NC}"
echo -e "${YELLOW}This script will help you test game state synchronization and persistence${NC}"
echo

# Check if the server is running
echo -e "${YELLOW}Checking if development server is running...${NC}"
if ! curl -s http://localhost:5000 > /dev/null; then
  echo -e "${YELLOW}Starting development servers...${NC}"
  ./start-dev.sh &
  sleep 5
  echo -e "${GREEN}Servers started${NC}"
else
  echo -e "${GREEN}Servers are already running${NC}"
fi

# Check if the database verification script exists
if [ -f "./verify-database.sh" ]; then
  echo -e "${YELLOW}Running database verification script...${NC}"
  chmod +x ./verify-database.sh
  ./verify-database.sh
else
  echo -e "${RED}Database verification script not found${NC}"
fi

echo
echo -e "${BLUE}=== GAME STATE SYNCHRONIZATION TEST INSTRUCTIONS ===${NC}"
echo
echo -e "${YELLOW}Step 1: Create two test users (skip if already done)${NC}"
echo "1. Open two DIFFERENT browsers (e.g., Chrome and Firefox)"
echo "   - This prevents cookie/session conflicts between the two users"
echo "2. In each browser, go to http://localhost:3000/register"
echo "3. Register two different users (one in each browser)"

echo
echo -e "${YELLOW}Step 2: Start matchmaking${NC}"
echo "1. Log in with both users in their respective browsers"
echo "2. Click 'Play' or 'Find Match' in both browsers"
echo "3. Wait for the match to be created"

echo
echo -e "${YELLOW}Step 3: Test game state synchronization${NC}"
echo "1. Make a move in one browser and verify it appears in the other"
echo "2. Close one browser tab completely"
echo "3. Reopen the chess game in a new tab with the same user"
echo "4. Verify the game state is properly recovered"

echo
echo -e "${YELLOW}Step 4: Test database persistence${NC}"
echo "1. Make several more moves between the two browsers"
echo "2. Close both browser tabs"
echo "3. Log back in with both users"
echo "4. Check if the game appears in match history"
echo "5. Verify all moves were properly recorded"

echo
echo -e "${GREEN}Opening browser windows for you...${NC}"
open -a "Google Chrome" "http://localhost:3000/login" 2>/dev/null || (
  echo -e "${YELLOW}Couldn't open Chrome automatically. Please open http://localhost:3000/login in your browser.${NC}"
)

# Try to open Firefox if available
open -a "Firefox" "http://localhost:3000/login" 2>/dev/null || (
  echo -e "${YELLOW}Couldn't open Firefox automatically. Please open http://localhost:3000/login in a different browser.${NC}"
)

echo
echo -e "${BLUE}=== MONITORING WEBSOCKET TRAFFIC ===${NC}"
echo -e "${GREEN}Starting WebSocket monitor to help debug connections...${NC}"

# Start websocket monitoring in the background
./monitor-websocket.sh &

echo -e "${GREEN}Test setup complete. Follow the steps above to test synchronization.${NC}"
