# ChessChain: Decentralized Chess Platform with Blockchain Verification

This document provides a comprehensive overview of the ChessChain project, explaining its architecture, components, and how everything works together.

## Table of Contents

1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Frontend Components](#frontend-components)
4. [Backend Components](#backend-components)
5. [Blockchain Components](#blockchain-components)
6. [User Authentication Flow](#user-authentication-flow)
7. [Game Matchmaking Process](#game-matchmaking-process) 
8. [Move Validation & Blockchain Verification](#move-validation--blockchain-verification)
9. [Testing Infrastructure](#testing-infrastructure)
10. [Development Tools](#development-tools)
11. [Known Issues](#known-issues)

## Project Overview

ChessChain is a decentralized chess platform that combines traditional chess gameplay with blockchain-based verification. Players generate cryptographic keypairs, sign their moves using Ed25519 (previously secp256k1) signatures, and these signed moves are verified and recorded on a blockchain. This creates a secure, tamper-proof chess experience where all moves can be verified independently.

Key features include:
- User registration with cryptographic identity (Ed25519 keypairs)
- Browser-based chess gameplay with real-time updates via WebSocket
- Matchmaking system for pairing players
- Move signing using private keys for verification
- Blockchain-based storage of game history with cryptographic proof
- A blockchain explorer to view verified game records

## System Architecture

The system is composed of three main components:

1. **Frontend**: React-based web application
2. **Backend**: Node.js server with WebSocket support
3. **Blockchain**: Custom implementation using Python

The architecture follows this flow:
1. Users register and receive Ed25519 keypairs
2. Players are matched through a WebSocket matchmaking queue
3. Moves are signed by the player's private key and sent to the backend
4. The backend verifies the signatures and updates the game state
5. Completed games are stored on the blockchain with signatures
6. The blockchain can be queried to verify the authenticity of games and moves

## Frontend Components

The frontend is built with React and provides the chess gameplay interface.

### Key Files and Components:

- **Register.jsx**: Handles user registration, generating Ed25519 keypairs
- **Login.jsx**: Authenticates users and verifies key ownership
- **Game.jsx**: Main chess game interface with WebSocket connectivity
- **services/api.js**: WebSocket connection handling and API calls
- **BlockchainExplorer.jsx**: Interface to view verified games on the blockchain

### Key Frontend Technologies:

- React for UI components
- chess.js for chess game logic
- react-chessboard for the visual chess interface
- TweetNaCl.js for Ed25519 cryptography
- WebSocket for real-time game updates

## Backend Components

The backend server manages authentication, game state, and connects to the blockchain.

### Key Files and Components:

- **src/index.js**: Main server entry point
- **src/utils/websocket.js**: WebSocket server for real-time game communication
- **src/services/blockchain-bridge.js**: Interface with blockchain component
- **src/utils/blockchain.js**: Signature verification and blockchain utilities
- **src/controllers/**: API endpoints for various functionality

### Key Backend Technologies:

- Node.js as the runtime environment
- Express.js for REST API
- WebSocket for real-time communication
- PostgreSQL for persistent storage
- Authentication middleware for security

## Blockchain Components

The blockchain system stores and verifies chess game history.

### Key Files and Components:

- **ChessChain/api.py**: Blockchain API endpoints
- **ChessChain/models/models.py**: Data models and verification logic
- **ChessChain/utils/**: Blockchain utilities like Merkle trees and networking

### Key Blockchain Technologies:

- Custom Python-based blockchain implementation
- Ed25519 for signature verification
- LMDB for local blockchain storage
- Merkle trees for efficient verification

## User Authentication Flow

1. **Registration**:
   - User provides username, email, and password in the Register.jsx component
   - Frontend generates an Ed25519 keypair using TweetNaCl.js
   - Private key is stored in localStorage, public key sent to server
   - User receives confirmation and is instructed to secure their private key
   - Keys are used for signing moves and verifying identity

2. **Login**:
   - User enters email and password
   - Server authenticates credentials
   - The frontend retrieves the stored private key for signing moves

## Game Matchmaking Process

1. **Queue Joining**:
   - Authenticated user connects to WebSocket server
   - User sends a "joinQueue" message to the server
   - Server adds user to matchmakingQueue array

2. **Pairing Algorithm**:
   - Server periodically checks matchmakingQueue (every 5 seconds)
   - If 2+ players are in queue, it pairs them in FIFO order
   - Server creates a match object with IDs, colors, and empty move history
   - Both players are notified via WebSocket with match details

3. **Game Initialization**:
   - Both players receive opponent details and piece color assignment
   - White player is given the first move
   - Game.jsx renders the chessboard with appropriate orientation
   - Players must agree to rules before starting the actual game

## Move Validation & Blockchain Verification

1. **Move Creation and Signing**:
   - Player makes a move on the chessboard interface
   - Frontend validates move using chess.js library
   - Move data is structured with game ID, player color, piece information
   - Frontend signs the move data using the player's Ed25519 private key
   - Signed move is sent to the backend via WebSocket

2. **Backend Verification**:
   - Server receives the move and verifies:
     - Player authentication and authorization
     - Game exists and is active
     - It's the player's turn
     - Move is valid according to chess rules
     - Signature is valid using the player's public key
   - If valid, server updates game state and notifies both players
   - If invalid, server rejects move and notifies the player

3. **Blockchain Recording**:
   - Completed games (checkmate, draw, resignation) are submitted to the blockchain
   - All move signatures are included to create a verifiable record
   - Blockchain nodes verify signatures before accepting the game record
   - Game is added to the blockchain and becomes immutable proof of play

## Testing Infrastructure

The project includes comprehensive testing tools for both development and verification.

### Key Testing Scripts:

- **test-two-players.sh**: Opens two browser instances for testing multiplayer functionality
- **test-signatures.sh**: Validates the Ed25519 signature system
- **test-blockchain-game.sh**: Tests complete workflow from game to blockchain
- **test-websocket-connection.sh**: Debug cross-browser WebSocket issues
- **monitor-matchmaking.sh**: Monitors the matchmaking process in real-time

### Testing Workflow:

1. Start development servers with `start-dev.sh`
2. Create test users and keys with `generate-test-keys.sh`
3. Run specific test scripts depending on what needs verification
4. Monitor logs and outputs to identify issues
5. Use the interactive test menu with `easy-test.sh`

## Development Tools

### Setup and Configuration:

1. **Start Development Environment**:
   - `./start-dev.sh` starts the backend, frontend, and blockchain servers
   - Backend runs on port 5000
   - Frontend runs on port 3000 (or 5173 depending on configuration)
   - Blockchain service runs on a specified port per configuration

2. **Database Setup**:
   - PostgreSQL is used for user data and game records
   - Schema includes users, games, moves, and authentication tables
   - Run `verify-database.sh` to check database configuration

3. **Monitoring and Debugging**:
   - `debug-backend.sh` shows backend server logs
   - `monitor-websocket.sh` displays WebSocket connection events
   - `monitor-matchmaking.sh` tracks player pairing
   - Browser console for frontend debugging
   - WebSocket debug panel by adding `?debug=websocket` to game URL

## Key Workflows in Detail

### Complete Game Flow:

1. User registers and receives Ed25519 keypair
2. User logs in and joins matchmaking queue
3. Server pairs players and creates a game
4. Players make moves, each signed with their private key
5. Server verifies signatures and updates game state
6. Game concludes (checkmate, draw, resignation)
7. Game record with all signed moves is submitted to blockchain
8. Blockchain verifies signatures and records the game
9. Game is now permanently verifiable through blockchain explorer

## Known Issues

1. **Cross-Browser Matchmaking**: 
   - Users from different browsers might experience issues with WebSocket connections
   - Solution: Dynamic WebSocket URL generation based on hostname to ensure consistent connections

2. **Key Management**:
   - Private keys stored in localStorage could be lost if browser data is cleared
   - Users must manually back up their keys or risk losing access

## Conclusion

ChessChain demonstrates how blockchain verification can be integrated with traditional gameplay to create a secure, verifiable gaming experience. The combination of real-time WebSocket communication, cryptographic signatures, and blockchain storage provides a unique approach to chess that prioritizes fair play and verification.
