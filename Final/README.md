# ChainChess - Blockchain-based Chess Platform

ChainChess is an innovative chess platform that combines traditional chess gameplay with blockchain technology for move verification. Players use cryptographic signatures to sign their moves, and all game history is securely stored using Merkle trees for verification.

## Recent Updates (May 16, 2025)

We've made significant improvements to the game state synchronization:

- **Fixed Board Rotation**: Solved the issue where boards would rotate unexpectedly during play
- **Opponent Information Display**: Fixed display of opponent names and ratings instead of "unknown"
- **Game State Synchronization**: Improved state synchronization between browsers
- **Database Storage**: Resolved issues with game data storage and UUID conversions
- **Connection Stability**: Enhanced WebSocket connection handling and reconnection logic

## Key Features

- **Cryptographically Verified Gameplay**: Each move is signed with the player's private key
- **Real-time Multiplayer**: WebSocket-based communication for instant play
- **Blockchain Principles**: Uses Merkle trees to ensure game integrity
- **Modern UI**: Clean, responsive interface built with React and Bootstrap
- **Secure Authentication**: JWT authentication with cryptographic key generation

## Project Structure

- **Frontend/**: React application with Bootstrap styling and chess board components
  - WebSocket client for real-time game updates
  - Cryptographic signing of moves
  - State management for game synchronization

- **backend/**: Node.js server with Express, WebSocket, and blockchain utilities
  - WebSocket server for real-time game communication
  - RESTful API endpoints for game management
  - Supabase integration for data persistence

## Quick Start Guide

### Start Development Environment

Start both frontend and backend servers:

```bash
./start-dev.sh
```

### Test Two-Player Functionality

Run the testing script to verify two-player game functionality:

```bash
./test-two-players.sh
```

### Monitor WebSocket Connections

To debug WebSocket connections in real-time:

```bash
./monitor-websocket.sh
```

### Verify Database Schema

To fix and validate database schema issues:

```bash
./verify-database.sh
```

### Supabase Setup

1. A Supabase project has been configured with the following details:
   - Project ID: imcthdgzjptegaupahyx
   - URL: https://imcthdgzjptegaupahyx.supabase.co
   - API Key is already configured in the backend .env file

2. Run the SQL code in `backend/src/db/schema.sql` in the Supabase SQL Editor to create the necessary database tables
3. For more detailed instructions, see [SUPABASE_SETUP.md](SUPABASE_SETUP.md)

### Configuration

1. Create a `.env` file in the backend directory:
   ```
   PORT=5000
   JWT_SECRET=your_jwt_secret_key
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_anon_key
   FRONTEND_URL=http://localhost:3000
   ```

2. Configure the frontend to connect to the backend in `vite.config.js` (already set up)

### Check Dependencies

Verify that all dependencies are installed correctly:

```bash
npm run check
```

### Run the Application

Start both the backend and frontend servers with a single command:

```bash
npm start
```

The backend will be available at http://localhost:5000 and the frontend at http://localhost:3000

## Detailed Setup Instructions

For more detailed setup instructions, see:
- [Backend Setup](backend/README.md)
- [Frontend Setup](Frontend/chess-website/README.md)
- [Deployment Guide](DEPLOYMENT.md)

### Quick Development Startup

1. Check if all dependencies are properly installed:
   ```
   ./check-dependencies.sh
   ```
   This script will verify Node.js, npm, and required dependencies for both frontend and backend.

2. Run both frontend and backend servers with a single command:
   ```
   ./start-dev.sh
   ```
   This will start the backend server on port 5000 and the frontend dev server on port 3000.

## Features

- **Cryptographically signed moves**: Each player's moves are signed with their private key
- **Blockchain verification**: Game history is secured using Merkle trees
- **Real-time gameplay**: WebSocket connection for instant updates
- **User authentication**: Secure login and registration with key generation

## Architecture

### Backend Components

- **WebSocket Server**: Handles real-time game communication
- **Express API**: RESTful endpoints for authentication and game management
- **Blockchain Utilities**: Functions for cryptographic signatures and Merkle trees
- **Supabase Integration**: Database for persistent storage

### Frontend Components

- **React Components**: Modern, responsive UI built with React and Bootstrap
- **Game Logic**: Chess.js integration for move validation
- **Crypto Tools**: Ethereum wallet integration for signing moves

## Security Notes

- In this demo version, private keys are stored in localStorage for simplicity
- In a production environment, consider more secure key management solutions
- The project uses cryptographic concepts from blockchain but does not run on an actual blockchain
