#!/bin/bash
# Start all components of the chess blockchain application

# Check for terminal-related utilities
if ! command -v osascript &> /dev/null; then
    echo "❌ This script requires osascript (macOS) to open terminal windows"
    exit 1
fi

# Set the base directory for the project
PROJECT_DIR="$(pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/Frontend/chess-website"

# Create a function to open a new terminal window and run a command
open_terminal_with_command() {
    local title="$1"
    local dir="$2"
    local cmd="$3"
    
    osascript -e "tell application \"Terminal\"
        do script \"echo \\\"🚀 Starting $title...\\\" && cd $dir && $cmd\"
        set custom title of front window to \"$title\"
    end tell"
}

echo "🚀 Starting Chess Blockchain Application..."

# Check if blockchain is running first (not strictly needed as backend will start it)
BLOCKCHAIN_RUNNING=$(curl -s http://localhost:8080/health || echo "not running")
if [[ "$BLOCKCHAIN_RUNNING" == *"status"* ]]; then
    echo "✅ Blockchain API already running"
else
    echo "🔄 Blockchain will be started by the backend"
fi

# Start backend
echo "🔄 Starting backend server..."
if [ ! -d "$BACKEND_DIR" ]; then
    echo "❌ Backend directory not found: $BACKEND_DIR"
    echo "Current directory: $(pwd)"
    exit 1
fi

echo "Checking if backend has required dependencies..."
if [ ! -f "$BACKEND_DIR/package.json" ]; then
    echo "❌ Backend package.json not found"
    exit 1
fi

# Check for node_modules
if [ ! -d "$BACKEND_DIR/node_modules" ]; then
    echo "⚠️ Installing backend dependencies first..."
    (cd "$BACKEND_DIR" && npm install)
fi

open_terminal_with_command "ChessChain Backend" "$BACKEND_DIR" "npm run dev"

# Wait for backend to be ready with timeout
echo "⏳ Waiting for backend to start..."
TIMEOUT=30
COUNT=0
while ! curl -s http://localhost:5000/api/health > /dev/null; do
    sleep 1
    COUNT=$((COUNT+1))
    if [ $COUNT -ge $TIMEOUT ]; then
        echo "❌ Timeout waiting for backend to start. Check the backend terminal for errors."
        exit 1
    fi
    if [ $((COUNT % 5)) -eq 0 ]; then
        echo "Still waiting for backend to start... ($COUNT seconds)"
    fi
done
echo "✅ Backend is running"

# Start frontend
echo "🔄 Starting frontend server..."
open_terminal_with_command "ChessChain Frontend" "$FRONTEND_DIR" "npm run dev"

# Wait for frontend to be ready
echo "⏳ Waiting for frontend to start..."
while ! curl -s http://localhost:5173/ > /dev/null; do
    sleep 1
done
echo "✅ Frontend is running"

# Open the app in the default browser
echo "🌐 Opening application in browser..."
open http://localhost:5173/

echo "✅ All systems are up and running!"
echo "📱 Frontend: http://localhost:5173/"
echo "🖥️ Backend: http://localhost:5000/"
echo "⛓️ Blockchain API: http://localhost:8080/"
echo ""
echo "🎮 To test with two users, run: ./test-blockchain-game.sh"
echo "🧩 To explore the blockchain, visit: http://localhost:5173/explorer"
