#!/bin/bash
# Start components of the chess blockchain application manually

# Set the base directory for the project
PROJECT_DIR="/Users/levandalbashvili/Documents/GitHub/KKL199/Final"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/Frontend/chess-website"
BLOCKCHAIN_DIR="$PROJECT_DIR/ChessChain"

# Show menu
echo "🚀 ChessChain Component Launcher"
echo "-------------------------------"
echo "1) Start Backend Only"
echo "2) Start Frontend Only"
echo "3) Start Blockchain API Only"
echo "4) Start Everything (Sequential)"
echo "5) Test Two Users"
echo "q) Quit"
echo

read -p "Select an option: " choice

case "$choice" in
    1)
        echo "🔄 Starting backend server..."
        cd "$BACKEND_DIR" || exit 1
        npm run dev
        ;;
    2)
        echo "🔄 Starting frontend server..."
        cd "$FRONTEND_DIR" || exit 1
        npm run dev
        ;;
    3)
        echo "🔄 Starting blockchain API..."
        cd "$BLOCKCHAIN_DIR" || exit 1
        python main.py --api
        ;;
    4)
        echo "🔄 Starting backend server..."
        cd "$BACKEND_DIR" || exit 1
        npm run dev &
        BACKEND_PID=$!
        
        echo "⏳ Waiting for backend to respond..."
        TIMEOUT=30
        COUNT=0
        while ! curl -s http://localhost:5000/api/health > /dev/null; do
            sleep 1
            COUNT=$((COUNT+1))
            if [ $COUNT -ge $TIMEOUT ]; then
                echo "❌ Backend failed to start in time"
                kill $BACKEND_PID 2>/dev/null
                exit 1
            fi
            echo -n "."
        done
        echo "✅ Backend started!"
        
        echo "🔄 Starting frontend server..."
        cd "$FRONTEND_DIR" || exit 1
        npm run dev &
        FRONTEND_PID=$!
        
        echo "⏳ Waiting for frontend to respond..."
        COUNT=0
        while ! curl -s http://localhost:5173/ > /dev/null; do
            sleep 1
            COUNT=$((COUNT+1))
            if [ $COUNT -ge $TIMEOUT ]; then
                echo "❌ Frontend failed to start in time"
                kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
                exit 1
            fi
            echo -n "."
        done
        echo "✅ Frontend started!"
        
        echo "✅ All components started, press Ctrl+C to stop all"
        wait
        ;;
    5)
        echo "🔄 Running two-user test..."
        "$PROJECT_DIR/test-blockchain-game.sh"
        ;;
    q|Q)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac
