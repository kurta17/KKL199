# ChainChess Backend

This is the backend service for ChainChess, a blockchain-based chess game that ensures fair play and immutable game history through cryptographic verification.

## Features

- User authentication with public/private key pairs
- Game state verification using blockchain principles
- Merkle tree implementation for game history integrity
- WebSocket for real-time game updates
- Integration with Supabase for data storage

## Setup

1. Install dependencies:
   ```
   npm install
   ```

2. Create a `.env` file in the root directory with the following variables:
   ```
   PORT=5000
   JWT_SECRET=your_jwt_secret
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_anon_key
   ```

3. Run the development server:
   ```
   npm run dev
   ```

## API Endpoints

### Authentication
- POST /api/auth/register - Register a new user
- POST /api/auth/login - Login with credentials

### Game
- GET /api/games - Get list of user's games
- GET /api/games/:id - Get specific game details
- POST /api/game/move - Submit a new chess move
- GET /api/game/verify/:id - Verify game integrity

## WebSocket Events

- joinQueue - Join matchmaking queue
- move - Broadcast move to opponent
- resign - Player resignation
- drawOffer - Offer a draw
- drawResponse - Accept or decline draw offer
