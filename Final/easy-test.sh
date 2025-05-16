#!/bin/bash
# Simplified startup script for ChessChain - more reliable

# Set the correct path to the project
PROJECT_DIR="/Users/levandalbashvili/Documents/GitHub/KKL199/Final"
BACKEND_DIR="${PROJECT_DIR}/backend"
FRONTEND_DIR="${PROJECT_DIR}/Frontend/chess-website"

echo "========================================================="
echo "🚀 ChessChain Testing Script"
echo "========================================================="

echo "Step 1: Start the backend (this will auto-start the blockchain)"
echo "--------------------------------------------------------"
echo "In a new Terminal window, run:"
echo "cd \"${BACKEND_DIR}\" && npm run dev"
echo 
echo "Wait until you see the message: 'Server running on port 5000'"
echo "--------------------------------------------------------"
read -p "Press Enter once the backend is running... " 

echo "Step 2: Start the frontend"
echo "--------------------------------------------------------"
echo "In another Terminal window, run:"
echo "cd \"${FRONTEND_DIR}\" && npm run dev"
echo 
echo "Wait until the Vite dev server starts"
echo "--------------------------------------------------------"
read -p "Press Enter once the frontend is running... " 

echo "Step 3: Test with two players"
echo "--------------------------------------------------------"
echo "Make sure both backend and frontend are running before continuing."
read -p "Ready to start the test with two players? (y/n): " ready

if [[ "$ready" != "y" && "$ready" != "Y" ]]; then
    echo "Test cancelled. Start the test manually when ready using:"
    echo "${PROJECT_DIR}/test-blockchain-game.sh"
    exit 0
fi

# Create test users and open browsers
"${PROJECT_DIR}/test-blockchain-game.sh"

echo "========================================================="
echo "🎮 Test game is running!"
echo "👀 After finishing the game, check the blockchain explorer:"
echo "http://localhost:5173/explorer"
echo "========================================================="
