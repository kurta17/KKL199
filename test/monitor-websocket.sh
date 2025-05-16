#!/bin/bash
# monitor-websocket.sh
# This script monitors WebSocket connections for the ChessWeb app

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== WEBSOCKET CONNECTION MONITOR ===${NC}"
echo -e "${YELLOW}This script will help you observe WebSocket connections in real-time${NC}"
echo

# Find the most recent log file
LATEST_LOG=$(find /tmp -name "*.log" -print | grep -i chessweb | sort | tail -n1)

if [ -z "$LATEST_LOG" ]; then
  echo -e "${RED}No log file found. Make sure the server is running.${NC}"
  echo -e "${YELLOW}Starting the server...${NC}"
  
  # Start the server if not running
  if ! curl -s http://localhost:5000 > /dev/null; then
    ./start-dev.sh &
    sleep 5
  fi
  
  # Try finding the log again
  LATEST_LOG=$(find /tmp -name "*.log" -print | grep -i chessweb | sort | tail -n1)
  
  if [ -z "$LATEST_LOG" ]; then
    echo -e "${RED}Still no log file found. Please start the server manually.${NC}"
    exit 1
  fi
fi

echo -e "${GREEN}Found log file: ${LATEST_LOG}${NC}"
echo -e "${YELLOW}Monitoring WebSocket connections...${NC}"
echo

# Check if we want to use tcpdump for more detailed monitoring
if [ "$1" == "--packet-capture" ]; then
  echo -e "${YELLOW}Starting detailed packet capture of WebSocket traffic on port 5000...${NC}"
  echo -e "${RED}This requires sudo access. Please enter your password when prompted.${NC}"
  echo -e "${GREEN}Press Ctrl+C to stop monitoring${NC}"
  echo
  
  # Monitor WebSocket traffic on port 5000
  sudo tcpdump -A -s 0 "tcp port 5000 and (((ip[2:2] - ((ip[0]&0xf)<<2)) - ((tcp[12]&0xf0)>>2)) != 0)" | grep --color=always -A 5 -B 5 "move\|match\|gameState\|drawOffer\|resign\|error"
else
  # Default log monitoring with enhanced pattern matching
  echo -e "${YELLOW}Monitoring server logs for WebSocket events...${NC}"
  echo -e "${GREEN}Press Ctrl+C to stop monitoring${NC}"
  echo

  # Highlight different events in different colors
  tail -f "$LATEST_LOG" | sed \
    -e "s/Client connected.*/${GREEN}&${NC}/" \
    -e "s/authenticated on WebSocket.*/${CYAN}&${NC}/" \
    -e "s/joined matchmaking queue.*/${MAGENTA}&${NC}/" \
    -e "s/^Error.*/${RED}&${NC}/" \
    -e "s/.*error.*/${RED}&${NC}/" \
    -e "s/match created.*/${YELLOW}&${NC}/" \
    -e "s/move validated.*/${BLUE}&${NC}/" \
    -e "s/Game state request.*/${CYAN}&${NC}/" \
    -e "s/Received game state.*/${CYAN}&${NC}/" \
    -e "s/Setting player color.*/${YELLOW}&${NC}/" \
    -e "s/Saved player color.*/${YELLOW}&${NC}/" \
    -e "s/Restoring player color.*/${GREEN}&${NC}/" \
    -e "s/Restoring game ID.*/${GREEN}&${NC}/" \
    -e "s/game state inconsistent.*/${RED}&${NC}/" \
    -e "s/Attempting to recover game state.*/${MAGENTA}&${NC}/" \
    -e "s/Connection restored.*/${GREEN}&${NC}/" \
  -e "s/Client disconnected.*/${RED}&${NC}/"
