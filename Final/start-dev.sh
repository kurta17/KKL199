#!/bin/bash

# Function to check if port is in use
port_in_use() {
  lsof -i:$1 >/dev/null 2>&1
  return $?
}

# Kill any processes on ports we need
if port_in_use 5000; then
  echo "Port 5000 is in use. Stopping previous processes..."
  lsof -ti:5000 | xargs kill -9 2>/dev/null
  sleep 1
fi

if port_in_use 3000; then
  echo "Port 3000 is in use. Stopping previous processes..."
  lsof -ti:3000 | xargs kill -9 2>/dev/null
  sleep 1
fi

# Save the root directory
ROOT_DIR="$(pwd)"

# Start backend server
echo "Starting backend server..."
cd "$ROOT_DIR/backend" || exit
npm run dev &
BACKEND_PID=$!

# Go to frontend directory
echo "Starting frontend server..."
cd "$ROOT_DIR/Frontend/chess-website" || {
  echo "Frontend directory not found at: $(pwd)/Frontend/chess-website"
  kill $BACKEND_PID
  exit 1
}

echo "Starting frontend server..."
npm run dev &
FRONTEND_PID=$!

echo "Development servers started."
echo "- Backend running at http://localhost:5000"
echo "- Frontend running at http://localhost:3000"

# Handle script termination
trap "echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID; exit" SIGINT SIGTERM

# Keep script running
wait
