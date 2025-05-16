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

echo "🔧 Creating test users if they don't exist..."
# Check if bypass route is available (for development) - add the name field
curl -s -X POST http://localhost:5000/api/bypass/register -H "Content-Type: application/json" -d "{\"email\":\"$TEST_USER1\",\"password\":\"$TEST_PASS\",\"username\":\"Player 1\",\"name\":\"Player 1\"}"
curl -s -X POST http://localhost:5000/api/bypass/register -H "Content-Type: application/json" -d "{\"email\":\"$TEST_USER2\",\"password\":\"$TEST_PASS\",\"username\":\"Player 2\",\"name\":\"Player 2\"}"

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
  # Try port 3000 first (current Vite port)
  if curl -s http://localhost:3000/ > /dev/null; then
    echo "3000"
  # Try port 5173 next (default Vite port)
  elif curl -s http://localhost:5173/ > /dev/null; then
    echo "5173"
  # Try port 3001 next (alternative port)
  elif curl -s http://localhost:3001/ > /dev/null; then
    echo "3001"
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
  
  # Generate a random position for the window
  x_pos=$((100 + RANDOM % 400))
  y_pos=$((100 + RANDOM % 200))

  echo "Opening game in $browser on port $frontend_port..."
  
  if [ "$browser" = "Google Chrome" ]; then
    # Using AppleScript to open Chrome with position and size
    osascript -e "
      tell application \"Google Chrome\"
        make new window with properties {bounds: {$x_pos, $y_pos, $((x_pos + 1000)), $((y_pos + 800))}}
        open location \"http://localhost:$frontend_port/login\"
        activate
      end tell
    "
  elif [ "$browser" = "Safari" ]; then
    # Using AppleScript to open Safari
    osascript -e "
      tell application \"Safari\"
        make new document
        set bounds of window 1 to {$x_pos, $y_pos, $((x_pos + 1000)), $((y_pos + 800))}
        set URL of document 1 to \"http://localhost:$frontend_port/login\"
        activate
      end tell
    "
  else
    # Firefox or other browser as fallback
    open -a "$browser" "http://localhost:$frontend_port/login"
  fi
  
  # Allow time for browser to open
  sleep 2
  
  # Use AppleScript to enter credentials and click login
  osascript -e "
    tell application \"System Events\"
      tell process \"$browser\"
        delay 1
        keystroke \"$email\"
        keystroke tab
        keystroke \"$password\"
        delay 0.5
        keystroke return
      end tell
    end tell
  "
}

echo "🎮 Opening game for Player 1 (in Chrome)..."
open_game_for_user $TEST_USER1 $TEST_PASS "Google Chrome"

sleep 3

echo "🎮 Opening game for Player 2 (in Safari)..."
open_game_for_user $TEST_USER2 $TEST_PASS "Safari"

echo "✅ Test users opened in separate browser windows"
frontend_port=$(detect_frontend_port)
echo "📊 After the game, check the blockchain explorer: http://localhost:$frontend_port/explorer"
echo "👁️ Once a game is complete, enter the Game ID in the explorer to verify all moves"
