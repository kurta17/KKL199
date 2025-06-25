#!/bin/bash
# test-two-players.sh
# This script helps test two-player functionality in the ChessChain application

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== CHESSCHAIN TWO-PLAYER TEST ===${NC}"
echo -e "${YELLOW}This script will help you test a complete two-player chess match${NC}"
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

# Register test users
echo -e "${YELLOW}Creating test users if they don't exist...${NC}"

# Check if users already exist before attempting to register
echo "Checking if users already exist..."
USER1_EXISTS=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:5000/api/bypass/login -H "Content-Type: application/json" -d "{\"email\":\"$TEST_USER1\",\"password\":\"$TEST_PASS\"}")
USER2_EXISTS=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:5000/api/bypass/login -H "Content-Type: application/json" -d "{\"email\":\"$TEST_USER2\",\"password\":\"$TEST_PASS\"}")

# Only register if users don't exist (if login returns 401)
if [ "$USER1_EXISTS" = "401" ]; then
  echo "Creating test user 1..."
  curl -s -X POST http://localhost:5000/api/bypass/register -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_USER1\",\"password\":\"$TEST_PASS\",\"username\":\"Player 1\",\"publicKey\":\"$TEST_PUB_KEY1\"}" > /dev/null
else
  echo -e "${GREEN}User 1 already exists, skipping registration${NC}"
fi

if [ "$USER2_EXISTS" = "401" ]; then
  echo "Creating test user 2..."
  curl -s -X POST http://localhost:5000/api/bypass/register -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_USER2\",\"password\":\"$TEST_PASS\",\"username\":\"Player 2\",\"publicKey\":\"$TEST_PUB_KEY2\"}" > /dev/null
else
  echo -e "${GREEN}User 2 already exists, skipping registration${NC}"
fi
echo
echo
echo -e "${BLUE}=== TWO-PLAYER TEST INSTRUCTIONS ===${NC}"
echo
echo -e "${YELLOW}Step 1: Login with test accounts${NC}"
echo "1. The script will open Chrome and Safari with the login page"
echo "2. Login using the provided test credentials"
echo
echo -e "${YELLOW}Step 2: Start matchmaking${NC}"
echo "1. Click 'Play' or 'Find Match' in both browsers"
echo "2. Wait for the match to be created"
echo "   - You should see a message that a match has been found"
echo
echo -e "${YELLOW}Step 3: Play the game${NC}"
echo "1. Make moves alternately in each browser"
echo "2. Verify that moves are properly signed and verified"
echo "3. Play until checkmate or draw"
echo
echo -e "${YELLOW}Step 4: Verify blockchain storage${NC}"
echo "1. After the game ends, check the blockchain explorer"
echo "2. Verify that all moves were properly signed and recorded"
echo

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

# Function to open browser to the game with the respective credentials
open_game_for_user() {
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
  login_url="http://localhost:$frontend_port/login?email=$email"

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
  
  # Display login instructions
  echo ""
  echo "⌨️  For $browser, please:"
  echo "   1. Enter email: $email"
  echo "   2. Enter password: $password" 
  echo "   3. Click Login"
  echo ""
}

echo -e "${GREEN}Opening browser windows for you...${NC}"

echo "🎮 Opening game for Player 1 (in Chrome)..."
open_game_for_user $TEST_USER1 $TEST_PASS "Google Chrome"

echo "⏳ Waiting to ensure first browser is ready..."
sleep 3

echo "🎮 Opening game for Player 2 (in Safari)..."
open_game_for_user $TEST_USER2 $TEST_PASS "Safari"

echo ""
echo "✅ Test users opened in separate browser windows"
echo "🔑 Login credentials:"
echo "   Player 1: $TEST_USER1 / $TEST_PASS"
echo "   Player 2: $TEST_USER2 / $TEST_PASS"
echo ""

frontend_port=$(detect_frontend_port)
echo "📊 After the game, check the blockchain explorer: http://localhost:$frontend_port/explorer"
echo "👁️ Once a game is complete, enter the Game ID in the explorer to verify all moves"
echo
echo -e "${BLUE}Happy testing!${NC}"
