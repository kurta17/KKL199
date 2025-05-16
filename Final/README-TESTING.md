# ChessChain: Blockchain-based Chess Game

This project implements a complete chess gaming application with blockchain-based move verification. 
The system consists of:

1. **Frontend**: React-based chess game interface with Tailwind CSS styling
2. **Backend**: Node.js server handling game logic and user management
3. **Blockchain**: Python-based ChessChain for cryptographic move verification

## Key Features

- **Blockchain Move Verification**: Every move is signed with the player's private key and verified on the blockchain
- **Cryptographic Identity**: Players have cryptographic keys for signing moves
- **Blockchain Explorer**: Verify game history and move authenticity after the game
- **Merkle Tree Validation**: Secure transaction validation using Merkle trees
- **Gossip Protocol**: P2P communication between blockchain nodes

## Testing the System with Two Users

To test the full system with two users playing against each other:

1. **Start the complete system**:
   ```
   ./start-all.sh
   ```
   This script starts the backend, frontend, and blockchain API in separate terminals.

2. **Run the two-player test**:
   ```
   ./test-blockchain-game.sh
   ```
   This opens two browser windows, each logged in with a different test user.

3. **Play the game**:
   - In the first window (Player 1), click "Play Game" to join the matchmaking queue
   - In the second window (Player 2), click "Play Game" to join the queue
   - The system will automatically match the players and start the game
   - Make moves with each player, taking turns

4. **Verify on the blockchain**:
   - After the game completes, note the Game ID
   - Visit http://localhost:5173/explorer
   - Enter the Game ID to verify all moves and their signatures

## System Architecture

```
                      ┌─────────────────┐
                      │                 │
                      │  React Frontend │
                      │                 │
                      └────────┬────────┘
                               │
                               │ HTTP/WS
                               ▼
┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │
│ Python ChessChain◄────┤  Node.js Backend│
│                 │    │                 │
└─────────────────┘    └─────────────────┘
```

## Technical Components

- **Blockchain**: Python implementation with IPv8 for P2P communication
- **Backend**: Express.js with WebSockets for real-time gameplay
- **Frontend**: React, chess.js, react-chessboard, Tailwind CSS
- **Cryptography**: ED25519 for signatures, SHA256 for hashing

## Security Notes

- In the current implementation, private keys are stored in browser localStorage
- For a production system, a more secure key storage solution would be recommended
- The blockchain node auto-starts when the backend starts

---

To explore the blockchain directly, visit http://localhost:8080/docs for the API documentation.
