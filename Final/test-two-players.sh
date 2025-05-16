#!/bin/bash
# test-two-players.sh
# This script helps test two-player functionality in the ChessWeb app

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== CHESS TWO-PLAYER TEST ===${NC}"
echo -e "${YELLOW}This script will help you test a complete two-player chess match${NC}"
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

echo
echo -e "${BLUE}=== TWO-PLAYER TEST INSTRUCTIONS ===${NC}"
echo
echo -e "${YELLOW}Step 1: Create two test users${NC}"
echo "1. Open two DIFFERENT browsers (e.g., Chrome and Firefox)"
echo "   - This prevents cookie/session conflicts between the two users"
echo "2. In each browser, go to http://localhost:3000/register"
echo "3. Register two different users (one in each browser)"
echo
echo -e "${YELLOW}Step 2: Start matchmaking${NC}"
echo "1. Log in with both users in their respective browsers"
echo "2. Click 'Play' or 'Find Match' in both browsers"
echo "3. Wait for the match to be created"
echo "   - You should see a message that a match has been found"
echo
echo -e "${YELLOW}Step 3: Play the game${NC}"
echo "1. Make moves alternately in each browser"
echo "2. Verify that moves are properly synchronized"
echo "3. Play until checkmate or draw"
echo
echo -e "${YELLOW}Step 4: Verify game storage${NC}"
echo "1. After the game ends, check that it appears in match history"
echo "2. Verify that all moves were properly recorded"
echo
echo -e "${GREEN}Opening browser windows for you...${NC}"

# Open browsers (if on macOS)
if [ "$(uname)" == "Darwin" ]; then
  open -a "Google Chrome" "http://localhost:3000/register"
  open -a "Safari" "http://localhost:3000/register" 
  echo -e "${GREEN}Browser windows opened!${NC}"
else
  echo -e "${YELLOW}Please manually open two different browsers to http://localhost:3000/register${NC}"
fi

echo
echo -e "${BLUE}=== OBSERVING MATCH DATA ===${NC}"
echo "To see WebSocket connections and game data in real-time, watch the server logs"
echo -e "${YELLOW}Command to view server logs:${NC}"
echo "tail -f \$(find /tmp -name \"*.log\" -print | grep chessweb | sort | tail -n1)"
echo
echo -e "${BLUE}Happy testing!${NC}"
