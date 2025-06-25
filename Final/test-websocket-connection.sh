#!/bin/bash
# test-websocket-connection.sh
# Script to debug WebSocket connections between different browsers

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== CHESSCHAIN WEBSOCKET CONNECTION TEST ===${NC}"
echo -e "${YELLOW}This script will help you test WebSocket connections between browsers${NC}"
echo

# Check if the server is running
echo -e "${YELLOW}Checking if development server is running...${NC}"
if ! curl -s http://localhost:5000/api/health > /dev/null; then
  echo -e "${YELLOW}Starting development servers...${NC}"
  ./start-dev.sh &
  sleep 5
  echo -e "${GREEN}Servers started${NC}"
else
  echo -e "${GREEN}Servers are already running${NC}"
fi

# Create test users
TEST_USER1='player1@test.com'
TEST_USER2='player2@test.com'
TEST_PASS='Test123!'

# Source test keypairs if available
if [ -f "test_keypairs.txt" ]; then
  echo -e "${GREEN}Using generated Ed25519 keys from test_keypairs.txt${NC}"
  source test_keypairs.txt
else
  # Generate test keys
  echo -e "${YELLOW}Generating Ed25519 keys for testing...${NC}"
  chmod +x generate-test-keys.sh
  ./generate-test-keys.sh
  source test_keypairs.txt
fi

# Function to detect the correct frontend port
detect_frontend_port() {
  # Store the available ports
  local available_ports=()
  
  # Try common frontend ports
  if curl -s http://localhost:3000/ > /dev/null; then
    available_ports+=("3000")
  fi
  
  if curl -s http://localhost:5173/ > /dev/null; then
    available_ports+=("5173")
  fi
  
  if curl -s http://localhost:3001/ > /dev/null; then
    available_ports+=("3001")
  fi
  
  # If we found any available port, return the first one
  # Prioritize port 3000 if it's available
  if [[ " ${available_ports[*]} " =~ " 3000 " ]]; then
    echo "3000"
  elif [ ${#available_ports[@]} -gt 0 ]; then
    echo "${available_ports[0]}"
  else
    # Default to 3000 if nothing is detected
    echo "3000" 
  fi
}

# Function to open browser to game debug page
open_connection_debug_for_user() {
  email=$1
  password=$2
  browser=$3
  frontend_port=$(detect_frontend_port)
  
  # Check if browser is already running
  if pgrep "$browser" > /dev/null; then
    echo "Browser $browser is already running, will use existing instance"
  fi
  
  # Generate a random position for the window
  x_pos=$((100 + RANDOM % 300))
  y_pos=$((100 + RANDOM % 150))
  
  # Generate a URL with email prefilled
  login_url="http://localhost:$frontend_port/login?email=$email&debug=websocket"

  echo "Opening game in $browser on port $frontend_port..."
  
  if [ "$browser" = "Google Chrome" ]; then
    open -a "Google Chrome" "$login_url"
    sleep 1
    osascript -e "
      tell application \"Google Chrome\"
        set bounds of front window to {$x_pos, $y_pos, $((x_pos + 900)), $((y_pos + 700))}
      end tell
    " || echo "Failed to position Chrome window"
  elif [ "$browser" = "Safari" ]; then
    open -a "Safari" "$login_url"
    sleep 1
    osascript -e "
      tell application \"Safari\"
        set bounds of front window to {$x_pos, $y_pos, $((x_pos + 900)), $((y_pos + 700))}
      end tell
    " || echo "Failed to position Safari window"
  else
    open -a "$browser" "$login_url"
  fi
  
  echo ""
  echo "⌨️  For $browser, please:"
  echo "   1. Enter email: $email"
  echo "   2. Enter password: $password" 
  echo "   3. Click Login"
  echo "   4. Open browser console (Command+Option+J in Chrome, Command+Option+C in Safari)"
  echo "   5. Check WebSocket connection logs"
  echo ""
}

echo -e "${GREEN}Opening browser windows for connection testing...${NC}"

echo "🎮 Opening for Player 1 (Chrome)..."
open_connection_debug_for_user $TEST_USER1 $TEST_PASS "Google Chrome"

echo "⏳ Waiting to ensure first browser is ready..."
sleep 3

echo "🎮 Opening for Player 2 (Safari)..."
open_connection_debug_for_user $TEST_USER2 $TEST_PASS "Safari"

echo ""
echo -e "${BLUE}WebSocket Connection Debugging Instructions:${NC}"
echo ""
echo -e "${YELLOW}1. Login with both accounts${NC}"
echo "2. In each browser, open the console (Command+Option+J in Chrome, Command+Option+C in Safari)"
echo "3. Look for WebSocket connection logs like:"
echo "   - 'Creating new WebSocket connection'"
echo "   - 'Connecting to WebSocket at ws://...'"
echo "   - 'WebSocket connected successfully'"
echo ""
echo -e "${YELLOW}4. Check authentication:${NC}"
echo "   - Look for 'Authenticating user: [user-id]'"
echo ""
echo -e "${YELLOW}5. Start matchmaking:${NC}"
echo "   - Click 'Play' or 'Find Match' in both browsers"
echo "   - Watch console for queue joining messages"
echo ""
echo -e "${YELLOW}6. Monitor backend logs:${NC}"
echo "   - Run './monitor-websocket.sh' in a separate terminal to watch backend logs"
echo ""
echo -e "${RED}If connections fail or players don't get matched:${NC}"
echo "   - Check that both browsers are using the same WebSocket URL format"
echo "   - Verify that both browsers can resolve the hostname correctly"
echo ""
echo -e "${BLUE}Happy debugging!${NC}"
