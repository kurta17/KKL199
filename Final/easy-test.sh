#!/bin/bash
# Interactive ChessChain testing menu

# Set the correct path to the project
PROJECT_DIR="/Users/levandalbashvili/Documents/GitHub/KKL199/Final"
BACKEND_DIR="${PROJECT_DIR}/backend"
FRONTEND_DIR="${PROJECT_DIR}/Frontend/chess-website"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}=========================================================${NC}"
echo -e "${YELLOW}🚀 ChessChain Interactive Testing Menu${NC}"
echo -e "${BLUE}=========================================================${NC}"

# Function to check if servers are running
check_servers() {
  local backend_running=false
  local frontend_running=false
  
  # Check if backend is running
  if curl -s http://localhost:5000/api/health > /dev/null; then
    backend_running=true
    echo -e "${GREEN}✅ Backend server is running${NC}"
  else
    echo -e "${YELLOW}❌ Backend server is not running${NC}"
  fi
  
  # Check if frontend is running (try multiple ports)
  if curl -s http://localhost:3000/ > /dev/null || curl -s http://localhost:5173/ > /dev/null; then
    frontend_running=true
    echo -e "${GREEN}✅ Frontend server is running${NC}"
  else
    echo -e "${YELLOW}❌ Frontend server is not running${NC}"
  fi
  
  # Return true if both are running
  if $backend_running && $frontend_running; then
    return 0
  else
    return 1
  fi
}

# Function to start servers if needed
ensure_servers_running() {
  if ! check_servers; then
    echo -e "\n${YELLOW}Starting servers...${NC}"
    
    # Start development servers
    echo -e "${CYAN}Running start-dev.sh...${NC}"
    "${PROJECT_DIR}/start-dev.sh" &
    
    echo -e "${YELLOW}Waiting for servers to start (15 seconds)...${NC}"
    sleep 15
    
    if check_servers; then
      echo -e "${GREEN}Servers started successfully!${NC}"
    else
      echo -e "${YELLOW}Server startup may not be complete. Continuing anyway...${NC}"
    fi
  fi
}

# Main menu
while true; do
  echo -e "\n${CYAN}Available tests:${NC}"
  echo -e "${YELLOW}1.${NC} Two Player Test ${CYAN}(Opens browsers for two users)${NC}"
  echo -e "${YELLOW}2.${NC} Ed25519 Signature Test ${CYAN}(Tests cryptographic signing)${NC}"
  echo -e "${YELLOW}3.${NC} Signature Verification Fix Test ${CYAN}(Comprehensive test)${NC}"
  echo -e "${YELLOW}4.${NC} Game State Test ${CYAN}(Tests game state synchronization)${NC}"
  echo -e "${YELLOW}5.${NC} Blockchain Test Game ${CYAN}(Full blockchain integration test)${NC}"
  echo -e "${YELLOW}6.${NC} WebSocket Connection Test ${CYAN}(Debugs matchmaking issues)${NC}"
  echo -e "${YELLOW}7.${NC} Monitor Matchmaking Queue ${CYAN}(Watches backend matchmaking)${NC}"
  echo -e "${YELLOW}8.${NC} Check Server Status${NC}"
  echo -e "${YELLOW}9.${NC} Start Servers${NC}"
  echo -e "${YELLOW}10.${NC} Exit${NC}"
  
  read -p "Enter your choice (1-10): " choice
  
  case $choice in
    1)
      echo -e "\n${BLUE}Running Two Player Test...${NC}"
      ensure_servers_running
      "${PROJECT_DIR}/test-two-players.sh"
      ;;
    2)
      echo -e "\n${BLUE}Running Ed25519 Signature Test...${NC}"
      "${PROJECT_DIR}/test-signatures.sh"
      ;;
    3)
      echo -e "\n${BLUE}Running Signature Verification Fix Test...${NC}"
      ensure_servers_running
      "${PROJECT_DIR}/test-signature-fix.sh"
      ;;
    4)
      echo -e "\n${BLUE}Running Game State Test...${NC}"
      ensure_servers_running
      "${PROJECT_DIR}/test-game-state.sh"
      ;;
    5)
      echo -e "\n${BLUE}Running Blockchain Test Game...${NC}"
      ensure_servers_running
      "${PROJECT_DIR}/test-blockchain-game.sh"
      ;;
    6)
      echo -e "\n${BLUE}Testing WebSocket Browser Connections...${NC}"
      ensure_servers_running
      "${PROJECT_DIR}/test-websocket-connection.sh"
      ;;
    7)
      echo -e "\n${BLUE}Monitoring Matchmaking Queue...${NC}"
      ensure_servers_running
      "${PROJECT_DIR}/monitor-matchmaking.sh"
      ;;
    8)
      echo -e "\n${BLUE}Checking Server Status...${NC}"
      check_servers
      ;;
    9)
      echo -e "\n${BLUE}Starting Servers...${NC}"
      "${PROJECT_DIR}/start-dev.sh" &
      sleep 10
      check_servers
      ;;
    10)
      echo -e "\n${GREEN}Thank you for testing ChessChain!${NC}"
      exit 0
      ;;
    *)
      echo -e "\n${YELLOW}Invalid choice. Please try again.${NC}"
      ;;
  esac
  
  echo -e "\n${BLUE}=========================================================${NC}"
  read -p "Press Enter to return to the main menu..."
  clear
done
