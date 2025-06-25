#!/bin/bash
# This script tests the chess game with two simulated users
# It opens two separate terminals, each logged in as a different user

# Check if all required processes are running
echo "🔍 Checking if all required services are running..."

# Check if backend is running
curl -s http://localhost:5000/api/health > /dev/null
if [ $? -ne 0 ]; then
  echo "❌ Backend server is not running! Start it first with:"
  echo "cd backend && npm run dev"
  exit 1
fi

# Check if blockchain is running via the API bridge
curl -s http://localhost:8080/health > /dev/null
if [ $? -eq 0 ]; then
  echo "✅ Blockchain node is running"
else
  echo "⚠️ Blockchain node might not be running! It will be started automatically by the backend"
fi

# Check if frontend is running (try multiple possible ports)
if curl -s http://localhost:3000/ > /dev/null || curl -s http://localhost:5173/ > /dev/null || curl -s http://localhost:3001/ > /dev/null; then
  echo "✅ Frontend is running"
else
  echo "❌ Frontend server is not running! Start it first with:"
  echo "cd Frontend/chess-website && npm run dev"
  exit 1
fi

echo "✅ All services appear to be running"

# Create test users - we'll create them if they don't exist
TEST_USER1='player1@test.com'
TEST_USER2='player2@test.com'
TEST_PASS='Test123!'

echo "🔧 Preparing test users..."

# Source the test keypairs if file exists
if [ -f "test_keypairs.txt" ]; then
  echo "Using generated Ed25519 keys from test_keypairs.txt"
  source test_keypairs.txt
else
  # Fallback to default Ed25519 public keys
  echo "Using default Ed25519 keys (consider running generate-test-keys.sh first)"
  TEST_PUB_KEY1="s6V/oLeMhvHqf6jNeoZN3BCW/GSQScvIXzoiQrGC2M0="
  TEST_PUB_KEY2="zWK3J1Di6r2IMN/SCbpZZjX30VICUpTU01woWo8m71I="
fi

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
  echo "User 1 already exists, skipping registration"
fi

if [ "$USER2_EXISTS" = "401" ]; then
  echo "Creating test user 2..."
  curl -s -X POST http://localhost:5000/api/bypass/register -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_USER2\",\"password\":\"$TEST_PASS\",\"username\":\"Player 2\",\"publicKey\":\"$TEST_PUB_KEY2\"}" > /dev/null
else
  echo "User 2 already exists, skipping registration"
fi

echo "Using public keys:"
echo "Player 1: ${TEST_PUB_KEY1}"
echo "Player 2: ${TEST_PUB_KEY2}"

# Check if bypass route is available (for development)
curl -s -X POST http://localhost:5000/api/bypass/register -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_USER1\",\"password\":\"$TEST_PASS\",\"username\":\"Player 1\",\"publicKey\":\"$TEST_PUB_KEY1\"}"
  
curl -s -X POST http://localhost:5000/api/bypass/register -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_USER2\",\"password\":\"$TEST_PASS\",\"username\":\"Player 2\",\"publicKey\":\"$TEST_PUB_KEY2\"}"

# Detect the default browser
detect_browser() {
  # Check if Chrome is installed
  if osascript -e 'tell application "System Events" to (name of processes) contains "Google Chrome"' | grep -q "true"; then
    echo "Google Chrome"
    return
  fi
  
  # Check if Safari is installed
  if osascript -e 'tell application "System Events" to (name of processes) contains "Safari"' | grep -q "true"; then
    echo "Safari"
    return
  fi
  
  # Check if Firefox is installed
  if osascript -e 'tell application "System Events" to (name of processes) contains "Firefox"' | grep -q "true"; then
    echo "Firefox"
    return
  fi
  
  # Default to Safari as fallback
  echo "Safari"
}

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
  browser=$3  # Now passed explicitly
  frontend_port=$(detect_frontend_port)
  
  # Check if browser is already running
  if pgrep "$browser" > /dev/null; then
    echo "Browser $browser is already running, will use existing instance"
  fi
  
  # Generate a random position for the window (with better constraints)
  x_pos=$((100 + RANDOM % 300))
  y_pos=$((100 + RANDOM % 150))
  
  # Generate a unique URL with credentials for easy testing
  login_url="http://localhost:$frontend_port/login?email=$email"

  echo "Opening game in $browser on port $frontend_port..."
  
  if [ "$browser" = "Google Chrome" ]; then
    # Using open command for more reliability
    open -a "Google Chrome" "$login_url"
    
    # Allow browser time to open
    sleep 1
    
    # Position window using AppleScript (more reliable than direct open)
    osascript -e "
      tell application \"Google Chrome\"
        set bounds of front window to {$x_pos, $y_pos, $((x_pos + 900)), $((y_pos + 700))}
      end tell
    " || echo "Failed to position Chrome window"
    
  elif [ "$browser" = "Safari" ]; then
    # Open Safari with the URL
    open -a "Safari" "$login_url"
    
    # Allow browser time to open
    sleep 1
    
    # Position window using AppleScript
    osascript -e "
      tell application \"Safari\"
        set bounds of front window to {$x_pos, $y_pos, $((x_pos + 900)), $((y_pos + 700))}
      end tell
    " || echo "Failed to position Safari window"
    
  else
    # Firefox or other browser as fallback
    open -a "$browser" "$login_url"
  fi
  
  # Allow time for browser to open
  sleep 2
  
  # Display instructions instead of automated login (more reliable)
  echo ""
  echo "⌨️  For $browser, please:"
  echo "   1. Enter email: $email"
  echo "   2. Enter password: $password" 
  echo "   3. Click Login"
  echo ""
}

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
