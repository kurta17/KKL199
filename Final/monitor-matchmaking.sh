#!/bin/bash
# monitor-matchmaking.sh
# Script to monitor the matchmaking queue status

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== CHESSCHAIN MATCHMAKING QUEUE MONITOR ===${NC}"
echo

# Check if the backend server is running
echo -e "${YELLOW}Checking if backend server is running...${NC}"
if ! curl -s http://localhost:5000/api/health > /dev/null; then
  echo -e "${RED}Backend server is not running. Please start it first.${NC}"
  echo -e "${YELLOW}You can run ./start-dev.sh to start all servers${NC}"
  exit 1
else
  echo -e "${GREEN}Backend server is running${NC}"
fi

echo -e "${YELLOW}Monitoring the WebSocket server logs for matchmaking events...${NC}"
echo -e "${CYAN}Press Ctrl+C to stop monitoring${NC}"
echo

# Watch the logs for matchmaking-related events
if [[ "$OSTYPE" == "darwin"* ]]; then
  # macOS version
  echo -e "${BLUE}Attaching to WebSocket logs (macOS)...${NC}"
  tail -f /tmp/chesschain-backend.log | grep -E 'joinQueue|joined matchmaking queue|matchmaking|creating match|Match created'
else
  # Linux version
  echo -e "${BLUE}Attaching to WebSocket logs (Linux)...${NC}"
  tail -f /tmp/chesschain-backend.log | grep -E 'joinQueue|joined matchmaking queue|matchmaking|creating match|Match created'
fi
