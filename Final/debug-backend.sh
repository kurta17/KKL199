#!/bin/bash
# Debug script to test starting just the backend

# Set the correct path to the backend
PROJECT_DIR="/Users/levandalbashvili/Documents/GitHub/KKL199/Final"
BACKEND_DIR="${PROJECT_DIR}/backend"

echo "🔎 Debug info:"
echo "Current directory: $(pwd)"
echo "Backend directory: ${BACKEND_DIR}"

if [ ! -d "$BACKEND_DIR" ]; then
    echo "❌ Backend directory not found: $BACKEND_DIR"
    exit 1
fi

echo "📂 Checking backend directory contents:"
ls -la "$BACKEND_DIR"

echo "📦 Checking package.json:"
if [ -f "$BACKEND_DIR/package.json" ]; then
    cat "$BACKEND_DIR/package.json" | grep -E '("name"|"scripts")'
else
    echo "❌ package.json not found!"
    exit 1
fi

echo "📋 Starting backend server directly:"
cd "$BACKEND_DIR" || exit 1
echo "Now in directory: $(pwd)"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Start the server in the current terminal
echo "🚀 Starting backend server..."
npm run dev
