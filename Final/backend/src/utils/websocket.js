// In-memory storage for active users and matches
const activeUsers = new Map(); // userId -> websocket connection
const matchmakingQueue = []; // array of users waiting for match
const activeMatches = new Map(); // matchId -> match object
const { submitMove, verifyMoveSignature } = require('../services/blockchain-bridge');

/**
 * Sets up the WebSocket server handlers
 * @param {WebSocket.Server} wss - WebSocket server instance
 */
function setupWebSocket(wss) {
  wss.on('connection', (ws, req) => {
    console.log(`Client connected from IP: ${req.socket.remoteAddress}`);
    let userId = null;
    let pingInterval = null;

    // Setup ping-pong to detect dead clients
    pingInterval = setInterval(() => {
      if (ws.readyState === ws.OPEN) {
        ws.ping(() => {});
      }
    }, 30000); // Send a ping every 30 seconds

    // Handle incoming messages
    ws.on('message', (message) => {
      try {
        const data = JSON.parse(message);
        
        // Log incoming message (excluding sensitive data)
        const logData = { ...data };
        if (logData.signature) logData.signature = '***signature***';
        console.log(`Received message from ${userId || 'unauthenticated user'}: ${JSON.stringify(logData)}`);
        
        // Require authentication for most message types
        if (!userId && data.type !== 'authenticate') {
          ws.send(JSON.stringify({
            type: 'error',
            message: 'Authentication required'
          }));
          return;
        }
        
        // Handle different message types
        switch (data.type) {
          case 'authenticate':
            handleAuth(ws, data.userId);
            userId = data.userId;
            break;
          case 'joinQueue':
            handleJoinQueue(ws, userId || data.userId);
            break;
          case 'move':
            handleMove(ws, userId, data.matchId, data.move, data.signature);
            break;
          case 'resign':
            handleResign(ws, userId, data.matchId);
            break;
          case 'drawOffer':
            handleDrawOffer(ws, userId, data.matchId);
            break;
          case 'drawResponse':
            handleDrawResponse(ws, userId, data.matchId, data.accepted);
            break;
          case 'getGameState':
            handleGetGameState(ws, userId, data.matchId);
            break;
          case 'ping':
            ws.send(JSON.stringify({ type: 'pong' }));
            break;
          default:
            console.log('Unknown message type:', data.type);
            ws.send(JSON.stringify({
              type: 'error',
              message: 'Unknown message type'
            }));
        }
      } catch (err) {
        console.error('Error processing message:', err);
        ws.send(JSON.stringify({
          type: 'error',
          message: 'Invalid message format'
        }));
      }
    });

    // Handle WebSocket errors
    ws.on('error', (error) => {
      console.error(`WebSocket error for user ${userId || 'unknown'}:`, error);
    });

    // Handle client disconnect
    ws.on('close', (code, reason) => {
      console.log(`Client disconnected. User ID: ${userId || 'unknown'}, Code: ${code}, Reason: ${reason || 'No reason provided'}`);
      clearInterval(pingInterval);
      if (userId) {
        handleDisconnect(userId);
      }
    });
  });

  // Set up periodic matchmaking checks
  setInterval(checkMatchmaking, 5000);
}

/**
 * Handle user authentication on WebSocket
 */
function handleAuth(ws, userId) {
  if (!userId) return;
  
  activeUsers.set(userId, ws);
  console.log(`User ${userId} authenticated on WebSocket`);
}

/**
 * Handle user joining matchmaking queue
 */
function handleJoinQueue(ws, userId) {
  if (!userId) {
    ws.send(JSON.stringify({ type: 'error', message: 'Not authenticated' }));
    return;
  }
  
  // Check if user is already in queue
  if (matchmakingQueue.includes(userId)) {
    return;
  }
  
  // Add user to queue
  matchmakingQueue.push(userId);
  console.log(`User ${userId} joined matchmaking queue`);
  ws.send(JSON.stringify({ type: 'queueJoined' }));
}

/**
 * Check for potential matches between players in queue
 */
function checkMatchmaking() {
  if (matchmakingQueue.length < 2) return;
  
  // Create matches from queue in FIFO order
  while (matchmakingQueue.length >= 2) {
    const user1Id = matchmakingQueue.shift();
    const user2Id = matchmakingQueue.shift();
    
    const user1Connection = activeUsers.get(user1Id);
    const user2Connection = activeUsers.get(user2Id);
    
    // Skip if either user disconnected
    if (!user1Connection || !user2Connection) {
      // Put active user back in queue
      if (user1Connection) matchmakingQueue.push(user1Id);
      if (user2Connection) matchmakingQueue.push(user2Id);
      continue;
    }
    
    // Create match
    const matchId = generateMatchId();
    const match = {
      id: matchId,
      players: {
        white: { id: user1Id },
        black: { id: user2Id }
      },
      moveHistory: [],
      startTime: new Date(),
    };
    
    activeMatches.set(matchId, match);
    
    // Fetch user details for both players
    fetchUserDetails(user1Id, user2Id).then(([user1Details, user2Details]) => {
      // Update match with full player details if available
      if (user1Details) {
        match.players.white = {
          ...match.players.white,
          ...user1Details
        };
      }
      
      if (user2Details) {
        match.players.black = {
          ...match.players.black,
          ...user2Details
        };
      }
      
      // Notify white player with black player details
      user1Connection.send(JSON.stringify({
        type: 'match',
        matchId,
        color: 'white',
        opponent: user2Details || { id: user2Id, username: `Player ${user2Id.substring(0, 8)}`, rating: 1200 }
      }));
      
      // Notify black player with white player details
      user2Connection.send(JSON.stringify({
        type: 'match',
        matchId,
        color: 'black',
        opponent: user1Details || { id: user1Id, username: `Player ${user1Id.substring(0, 8)}`, rating: 1200 }
      }));
      
      console.log(`Match created: ${matchId} between ${user1Details?.username || user1Id} and ${user2Details?.username || user2Id}`);
    }).catch(err => {
      console.error('Error fetching player details:', err);
      
      // Fallback to basic notification without additional details
      user1Connection.send(JSON.stringify({
        type: 'match',
        matchId,
        color: 'white',
        opponent: { id: user2Id, username: `Player ${user2Id.substring(0, 8)}`, rating: 1200 }
      }));
      
      user2Connection.send(JSON.stringify({
        type: 'match',
        matchId,
        color: 'black',
        opponent: { id: user1Id, username: `Player ${user1Id.substring(0, 8)}`, rating: 1200 }
      }));
      
      console.log(`Match created with fallback details: ${matchId} between ${user1Id} and ${user2Id}`);
    });
  }
}

/**
 * Handle a move from a player with improved synchronization
 */
function handleMove(ws, userId, matchId, move, signature) {
  if (!userId || !matchId || !move) {
    ws.send(JSON.stringify({ type: 'error', message: 'Invalid move data' }));
    return;
  }
  
  const match = activeMatches.get(matchId);
  if (!match) {
    ws.send(JSON.stringify({ type: 'error', message: 'Match not found' }));
    return;
  }
  
  // Check if user is part of this match
  const isWhite = match.players.white.id === userId;
  const isBlack = match.players.black.id === userId;
  if (!isWhite && !isBlack) {
    ws.send(JSON.stringify({ type: 'error', message: 'Not a player in this match' }));
    return;
  }
  
  // Check if it's this player's turn based on move history length
  // Even number of moves (0, 2, 4...) = white's turn, Odd = black's turn
  const currentPlayerColor = isWhite ? 'white' : 'black';
  const isPlayerTurn = (match.moveHistory.length % 2 === 0 && currentPlayerColor === 'white') || 
                      (match.moveHistory.length % 2 === 1 && currentPlayerColor === 'black');
  
  if (!isPlayerTurn) {
    ws.send(JSON.stringify({ 
      type: 'error', 
      message: 'Not your turn',
      details: {
        moveCount: match.moveHistory.length,
        yourColor: currentPlayerColor
      }
    }));
    return;
  }
  
  // Validate move structure
  if (!move.from || !move.to) {
    ws.send(JSON.stringify({ type: 'error', message: 'Invalid move format (missing from/to)' }));
    return;
  }
  
  // Validate promotion if included
  if (move.promotion && !['q', 'r', 'b', 'n'].includes(move.promotion)) {
    ws.send(JSON.stringify({ type: 'error', message: 'Invalid promotion piece' }));
    return;
  }
  
  // Get player's public key
  const playerObj = isWhite ? match.players.white : match.players.black;
  const publicKey = playerObj.publicKey;
  
  if (!publicKey) {
    console.error(`Public key not found for user ${userId}`);
  }
  
  // Create a move object to be recorded on the blockchain
  const moveData = {
    gameId: matchId,
    moveNumber: match.moveHistory.length,
    fromSquare: move.from,
    toSquare: move.to,
    piece: move.piece || getPieceFromFen(move.fen, move.from),
    promotion: move.promotion || null,
    playerColor: currentPlayerColor,
    timestamp: Date.now()
  };
  
  // Verify move signature with the blockchain bridge
  verifyMoveSignature(moveData, signature, publicKey)
    .then(isValid => {
      if (!isValid && signature) {
        ws.send(JSON.stringify({ 
          type: 'error', 
          message: 'Invalid move signature. Please verify your private key.' 
        }));
        return;
      }
      
      // If we get here, either signature is valid or we're accepting without verification
      if (!signature) {
        console.warn(`Move accepted without signature verification for match ${matchId}`);
      }
      
      // Create a more detailed move record
      const moveRecord = {
        from: move.from,
        to: move.to,
        player: currentPlayerColor,
        timestamp: Date.now(),
        signature: signature || 'unsigned',
        piece: moveData.piece,
        promotion: move.promotion || null,
        capture: move.capture || false,
        check: move.check || false,
        fen: move.fen || null, // FEN after move
        gameState: move.gameState || null // Game state after move (checkmate, stalemate, etc.)
      };
      
      // Add move to history
      match.moveHistory.push(moveRecord);
      
      // Submit move to blockchain if signature is provided
      if (signature && publicKey) {
        submitMove({
          moveData,
          signature,
          publicKey
        }).then(() => {
          console.log(`Move submitted to blockchain for match ${matchId}`);
        }).catch(err => {
          console.error(`Error submitting move to blockchain for match ${matchId}:`, err);
        });
      }
      
      // Check if this move ends the game (checkmate, stalemate, etc.)
      let gameOver = false;
      if (move.gameState === 'checkmate') {
        match.status = 'completed';
        match.result = {
          winner: currentPlayerColor,
          reason: 'checkmate'
        };
        gameOver = true;
      } else if (move.gameState === 'stalemate' || move.gameState === 'insufficient' || 
                move.gameState === 'threefold' || move.gameState === 'fifty-move') {
        match.status = 'completed';
        match.result = {
          winner: 'draw',
          reason: move.gameState
        };
        gameOver = true;
      }
      
      // Continue with the existing logic to notify players
      // ...
    })
    .catch(err => {
      console.error('Error verifying move signature:', err);
      ws.send(JSON.stringify({ 
        type: 'error', 
        message: 'Error verifying move signature' 
      }));
    });
}

/**
 * Extract piece information from FEN string and square
 */
function getPieceFromFen(fen, square) {
  if (!fen) return 'p'; // Default to pawn if no FEN
  
  try {
    const fenParts = fen.split(' ');
    const boardPosition = fenParts[0];
    const rows = boardPosition.split('/');
    
    // Convert square (e.g. "e4") to row and column indices
    const col = square.charCodeAt(0) - 'a'.charCodeAt(0);
    const row = 8 - parseInt(square[1]);
    
    if (row < 0 || row >= 8 || col < 0 || col >= 8) {
      return 'p'; // Invalid square
    }
    
    // Read through FEN to find the piece at this position
    let currentRow = rows[row];
    let currentCol = 0;
    
    for (let char of currentRow) {
      if (/\d/.test(char)) {
        // Skip empty squares
        currentCol += parseInt(char);
      } else {
        // Found a piece
        if (currentCol === col) {
          // Convert FEN piece notation to our format
          const pieceType = char.toLowerCase();
          return pieceType;
        }
        currentCol++;
      }
      
      if (currentCol > col) {
        break;
      }
    }
    
    return 'p'; // Default to pawn if not found
  } catch (e) {
    console.error('Error extracting piece from FEN:', e);
    return 'p';
  }
}

/**
 * Handle player resignation with clear messaging
 */
function handleResign(ws, userId, matchId) {
  console.log(`Handling resignation from user ${userId} in match ${matchId}`);
  
  if (!userId || !matchId) {
    console.log('Resignation missing userId or matchId');
    ws.send(JSON.stringify({ 
      type: 'error', 
      message: 'Missing userId or matchId for resignation'
    }));
    return;
  }
  
  const match = activeMatches.get(matchId);
  if (!match) {
    console.log(`Resignation for non-existent match: ${matchId}`);
    ws.send(JSON.stringify({ 
      type: 'error', 
      message: 'Match not found'
    }));
    return;
  }
  
  // Check if user is part of this match
  const isWhite = match.players.white.id === userId;
  const isBlack = match.players.black.id === userId;
  
  if (!isWhite && !isBlack) {
    console.log(`User ${userId} not part of match ${matchId}`);
    ws.send(JSON.stringify({ 
      type: 'error', 
      message: 'You are not a player in this match'
    }));
    return;
  }
  
  // Check if match is already completed
  if (match.status === 'completed') {
    console.log(`Match ${matchId} already completed, ignoring resignation`);
    ws.send(JSON.stringify({ 
      type: 'error', 
      message: 'This match is already completed'
    }));
    return;
  }
  
  // Determine winner and resigning player
  const winner = isWhite ? 'black' : 'white';
  const resigningPlayer = isWhite ? 'white' : 'black';
  const winningPlayerId = isWhite ? match.players.black.id : match.players.white.id;
  
  console.log(`Player ${resigningPlayer} (${userId}) resigned. Winner: ${winner} (${winningPlayerId})`);
  
  // Update match status
  match.status = 'completed';
  match.result = {
    winner,
    reason: 'resignation',
    resigningPlayer,
    resigningPlayerId: userId,
    winningPlayerId
  };
  
  // Record resignation in move history
  match.moveHistory.push({
    type: 'resignation',
    player: resigningPlayer,
    timestamp: new Date(),
    signature: 'resignation'
  });
  
  // Send specific confirmation to the resigning player
  ws.send(JSON.stringify({
    type: 'resignConfirmed',
    matchId,
    message: 'You resigned the game',
    result: {
      winner,
      reason: 'resignation',
      resigningPlayer,
      outcome: 'loss'
    }
  }));
  
  // Send specific notification to the winning player
  const winnerConnection = activeUsers.get(winningPlayerId);
  if (winnerConnection) {
    winnerConnection.send(JSON.stringify({
      type: 'gameOver',
      matchId,
      message: 'Your opponent resigned',
      result: {
        winner,
        reason: 'resignation',
        resigningPlayer,
        outcome: 'win'
      }
    }));
  }
  
  // Also send a general notification to both players
  notifyBothPlayers(match, {
    type: 'matchEnded',
    matchId,
    status: 'completed',
    result: {
      winner,
      reason: 'resignation',
      resigningPlayer
    }
  });
  
  // Save the match to database
  saveMatchToDatabase(match);
  
  console.log(`Match ${matchId} ended by resignation. Winner: ${winner} (${winningPlayerId})`);
}

/**
 * Handle draw offers
 */
function handleDrawOffer(ws, userId, matchId) {
  if (!userId || !matchId) return;
  
  const match = activeMatches.get(matchId);
  if (!match) return;
  
  // Check if user is part of this match
  const isWhite = match.players.white.id === userId;
  const isBlack = match.players.black.id === userId;
  if (!isWhite && !isBlack) return;
  
  // Set draw offer
  match.drawOfferBy = userId;
  
  // Notify opponent
  const opponentId = isWhite ? match.players.black.id : match.players.white.id;
  const opponentConnection = activeUsers.get(opponentId);
  
  if (opponentConnection) {
    opponentConnection.send(JSON.stringify({
      type: 'drawOffer',
      matchId
    }));
  }
}

/**
 * Handle responses to draw offers
 */
function handleDrawResponse(ws, userId, matchId, accepted) {
  if (!userId || !matchId) return;
  
  const match = activeMatches.get(matchId);
  if (!match || !match.drawOfferBy) return;
  
  // Check if user is part of this match and not the one who offered
  if (match.drawOfferBy === userId) return;
  
  // Check if user is part of this match
  const isWhite = match.players.white.id === userId;
  const isBlack = match.players.black.id === userId;
  if (!isWhite && !isBlack) return;
  
  if (accepted) {
    // End game in draw
    match.status = 'completed';
    match.result = {
      winner: null,
      reason: 'draw_agreement'
    };
    
    // Notify both players
    notifyBothPlayers(match, {
      type: 'gameOver',
      matchId,
      result: {
        winner: null,
        reason: 'draw_agreement'
      }
    });
    
    // Save match to database (to be implemented)
    saveMatchToDatabase(match);
  } else {
    // Clear draw offer
    match.drawOfferBy = null;
    
    // Notify draw offerer
    const offererConnection = activeUsers.get(match.drawOfferBy);
    if (offererConnection) {
      offererConnection.send(JSON.stringify({
        type: 'drawDeclined',
        matchId
      }));
    }
  }
}

/**
 * Handle requests for current game state (used when clients reconnect or refresh browser)
 */
function handleGetGameState(ws, userId, matchId) {
  console.log(`Game state request from user ${userId} for match ${matchId}`);
  
  if (!userId || !matchId) {
    ws.send(JSON.stringify({ 
      type: 'error', 
      message: 'Missing userId or matchId for game state request'
    }));
    return;
  }
  
  const match = activeMatches.get(matchId);
  if (!match) {
    console.log(`Game state request for non-existent match: ${matchId}`);
    
    // Try to fetch from database if not in memory
    retrieveGameFromDatabase(matchId)
      .then(gameData => {
        if (gameData) {
          ws.send(JSON.stringify({
            type: 'gameState',
            matchId,
            state: {
              status: gameData.status,
              result: gameData.result ? JSON.parse(gameData.result) : null,
              moves: gameData.moves || [],
              isArchived: true
            }
          }));
        } else {
          ws.send(JSON.stringify({ 
            type: 'error', 
            message: 'Match not found in active games or database'
          }));
        }
      })
      .catch(error => {
        console.error('Error retrieving game from database:', error);
        ws.send(JSON.stringify({ 
          type: 'error', 
          message: 'Error retrieving game data'
        }));
      });
    return;
  }
  
  // Check if user is part of this match
  const isWhite = match.players.white.id === userId;
  const isBlack = match.players.black.id === userId;
  
  if (!isWhite && !isBlack) {
    console.log(`User ${userId} not part of match ${matchId}`);
    ws.send(JSON.stringify({ 
      type: 'error', 
      message: 'You are not a player in this match'
    }));
    return;
  }
  
  // Get the current player's color
  const playerColor = isWhite ? 'white' : 'black';
  
  // Get opponent details
  const opponentColor = isWhite ? 'black' : 'white';
  const opponentDetails = match.players[opponentColor];
  
  // If we only have opponent ID but not full details, try to fetch them
  if (opponentDetails && opponentDetails.id && !opponentDetails.username) {
    fetchUserDetails(opponentDetails.id, null).then(([userDetails]) => {
      if (userDetails) {
        // Update match with fetched details
        match.players[opponentColor] = {
          ...match.players[opponentColor],
          ...userDetails
        };
      }
    }).catch(err => {
      console.error('Error fetching opponent details:', err);
    });
  }
  
  // Get the last move if any
  const lastMove = match.moveHistory.length > 0 ? 
    match.moveHistory[match.moveHistory.length - 1] : null;
  
  // Format opponent information with defaults for missing fields
  const opponent = {
    id: opponentDetails.id,
    username: opponentDetails.username || `Player ${opponentDetails.id.substring(0, 8)}`,
    rating: opponentDetails.rating || 1200,
    wins: opponentDetails.wins || 0,
    losses: opponentDetails.losses || 0
  };
  
  // Send game state to the requesting player
  ws.send(JSON.stringify({
    type: 'gameState',
    matchId,
    playerColor,
    opponent,
    state: {
      status: match.status || 'active',
      result: match.result || null,
      moveHistory: match.moveHistory || [],
      lastMove: lastMove ? {
        from: lastMove.from,
        to: lastMove.to,
        piece: lastMove.piece,
        promotion: lastMove.promotion,
        fen: lastMove.fen
      } : null,
      drawOffer: match.drawOfferBy ? (match.drawOfferBy !== userId) : false,
      currentTurn: (match.moveHistory.length % 2 === 0) ? 'white' : 'black'
    }
  }));
  
  console.log(`Game state sent to player ${playerColor} (${userId}) for match ${matchId}`);
}

/**
 * Handle user disconnection
 */
function handleDisconnect(userId) {
  // Remove from active users
  activeUsers.delete(userId);
  
  // Remove from matchmaking queue
  const queueIndex = matchmakingQueue.indexOf(userId);
  if (queueIndex !== -1) {
    matchmakingQueue.splice(queueIndex, 1);
  }
  
  // Handle active matches
  for (const [matchId, match] of activeMatches.entries()) {
    if (match.players.white.id === userId || match.players.black.id === userId) {
      // Only mark as disconnected for now
      // Could implement reconnect logic or auto-forfeit after timeout
      if (match.players.white.id === userId) {
        match.players.white.disconnected = true;
      } else {
        match.players.black.disconnected = true;
      }
    }
  }
}

/**
 * Notify both players in a match with a message
 */
function notifyBothPlayers(match, message) {
  const whiteConnection = activeUsers.get(match.players.white.id);
  const blackConnection = activeUsers.get(match.players.black.id);
  
  if (whiteConnection) {
    whiteConnection.send(JSON.stringify(message));
  }
  
  if (blackConnection) {
    blackConnection.send(JSON.stringify(message));
  }
}

/**
 * Save match data to the database with Supabase
 */
async function saveMatchToDatabase(match) {
  try {
    const { supabase, supabaseAdmin } = require('./supabase');
    console.log('Saving match to database:', match.id);
    
    // For logging and debugging purposes
    const matchDebugInfo = {
      id: match.id,
      white_player: match.players.white.id,
      black_player: match.players.black.id,
      status: match.status,
      moveCount: match.moveHistory ? match.moveHistory.length : 0
    };
    console.log('Match to be saved:', matchDebugInfo);
    
    // Generate a consistent UUID from a string ID using v5 UUID algorithm
    function generateConsistentUUID(str) {
      const crypto = require('crypto');
      const namespace = '6ba7b810-9dad-11d1-80b4-00c04fd430c8'; // Fixed namespace
      
      // Calculate SHA-1 hash of namespace concatenated with string
      const hash = crypto.createHash('sha1')
        .update(namespace + str)
        .digest();
      
      // Format as UUID (version 5 - SHA-1 namespace)
      hash[6] = (hash[6] & 0x0f) | 0x50; // Set version to 5
      hash[8] = (hash[8] & 0x3f) | 0x80; // Set variant
      
      return hash.slice(0, 16).toString('hex')
        .replace(/(.{8})(.{4})(.{4})(.{4})(.{12})/, '$1-$2-$3-$4-$5');
    }
    
    // Format the match data for database insertion - fix for DB schema compatibility
    const gameData = {
      id: match.id,
      white_player_id: match.players.white.id,
      black_player_id: match.players.black.id,
      status: match.status || 'completed',
      result: match.result ? JSON.stringify(match.result) : null,
      created_at: match.startTime,
      started_at: match.startTime,
      completed_at: new Date()
      // Remove 'moves' field as it doesn't exist in the games table schema
    };
    
    // Convert string IDs to UUIDs if needed
    try {
      // Check if id isn't already a UUID format
      if (gameData.id && typeof gameData.id === 'string' && 
          !gameData.id.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)) {
        gameData.string_id = gameData.id; // Store original string ID
        gameData.id = generateConsistentUUID(gameData.id);
        console.log(`Converted string ID ${gameData.string_id} to UUID ${gameData.id}`);
      }
      
      // Also ensure player IDs are UUIDs
      ['white_player_id', 'black_player_id'].forEach(field => {
        const playerId = gameData[field];
        if (playerId && typeof playerId === 'string' && 
            !playerId.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)) {
          gameData[`${field}_original`] = playerId;
          gameData[field] = generateConsistentUUID(playerId);
          console.log(`Converted player ID ${playerId} to UUID ${gameData[field]}`);
        }
      });
    } catch (err) {
      console.error('Error converting IDs to UUID format:', err);
    }
    
    console.log('Prepared game data:', gameData);
    
    // First, ensure both players exist in the users table
    await ensurePlayersExist(match.players.white.id, match.players.black.id);
    
    // Try multiple approaches to save the game
    let saved = false;
    let gameRecord = null;
    
    // Approach 1: Use admin client to bypass RLS
    try {
      const { data, error } = await supabaseAdmin
        .from('games')
        .insert([gameData])
        .select();
        
      if (!error) {
        saved = true;
        gameRecord = data;
        console.log('Game saved successfully with admin client');
      } else {
        console.error('Error saving with admin client:', error);
      }
    } catch (e) {
      console.error('Exception during admin save:', e);
    }
    
    // Approach 2: Try direct SQL insert if admin client fails
    if (!saved && supabaseAdmin) {
      try {
        // Use raw SQL instead of non-existent RPC function
        const { data, error } = await supabaseAdmin.from('games').insert([{
          id: gameData.id,
          white_player_id: gameData.white_player_id,
          black_player_id: gameData.black_player_id,
          status: gameData.status,
          result: gameData.result,
          created_at: gameData.created_at,
          started_at: gameData.started_at,
          completed_at: gameData.completed_at
        }]).select();
        
        if (!error) {
          saved = true;
          gameRecord = data;
          console.log('Game saved successfully with direct SQL insert');
        } else {
          console.error('Error saving with direct SQL insert:', error);
        }
      } catch (e) {
        console.error('Exception during SQL insert:', e);
      }
    }
    
    // Approach 3: Try direct user client as a last resort
    if (!saved) {
      try {
        const { data, error } = await supabase
          .from('games')
          .insert([gameData])
          .select();
          
        if (!error) {
          saved = true;
          gameRecord = data;
          console.log('Game saved successfully with regular client');
        } else {
          console.error('Error saving with regular client:', error);
        }
      } catch (e) {
        console.error('Exception during regular save:', e);
      }
    }
    
    // If we successfully saved the game, save the moves
    if (saved && match.moveHistory && match.moveHistory.length > 0) {
      await saveMoves(match.id, match.moveHistory);
      
      // Update player statistics (wins, losses, etc.)
      if (match.result && match.result.winner) {
        await updatePlayerStats(match);
      }
      
      return true;
    } else {
      console.error('Failed to save game after multiple attempts');
      return false;
    }
  } catch (error) {
    console.error('Exception while saving match:', error);
    return false;
  }
}

/**
 * Ensure both players exist in the database before saving a match
 */
async function ensurePlayersExist(whitePlayerId, blackPlayerId) {
  const { supabase, supabaseAdmin } = require('./supabase');
  
  try {
    // Check if players exist
    const { data: whitePlayers, error: whiteError } = await supabase
      .from('users')
      .select('id')
      .eq('id', whitePlayerId);
      
    const { data: blackPlayers, error: blackError } = await supabase
      .from('users')
      .select('id')
      .eq('id', blackPlayerId);
    
    const whitePlayerExists = whitePlayers && whitePlayers.length > 0;
    const blackPlayerExists = blackPlayers && blackPlayers.length > 0;
    
    console.log(`Player check: White exists: ${whitePlayerExists}, Black exists: ${blackPlayerExists}`);
    
    // Create missing players if needed
    if (!whitePlayerExists) {
      const whitePlayerData = {
        id: whitePlayerId,
        username: `player_${whitePlayerId.substring(0, 8)}`,
        email: `player_${whitePlayerId.substring(0, 8)}@demo.com`,
        public_key: '0x' + '0'.repeat(40),
        rating: 1200
      };
      
      // Try first with supabaseAdmin which should have service role privileges
      const { error: adminWhiteError } = await supabaseAdmin
        .from('users')
        .insert([whitePlayerData]);
        
      if (adminWhiteError) {
        console.error('Failed to create white player with admin client:', adminWhiteError);
        
        // Fallback to regular client
        const { error: regularWhiteError } = await supabase
          .from('users')
          .insert([whitePlayerData]);
          
        if (regularWhiteError) {
          console.error('Failed to create white player with regular client:', regularWhiteError);
        }
      } else {
        console.log('Created white player successfully');
      }
    }
    
    if (!blackPlayerExists) {
      const blackPlayerData = {
        id: blackPlayerId,
        username: `player_${blackPlayerId.substring(0, 8)}`,
        email: `player_${blackPlayerId.substring(0, 8)}@demo.com`,
        public_key: '0x' + '0'.repeat(40),
        rating: 1200
      };
      
      // Try first with supabaseAdmin
      const { error: adminBlackError } = await supabaseAdmin
        .from('users')
        .insert([blackPlayerData]);
        
      if (adminBlackError) {
        console.error('Failed to create black player with admin client:', adminBlackError);
        
        // Fallback to regular client
        const { error: regularBlackError } = await supabase
          .from('users')
          .insert([blackPlayerData]);
          
        if (regularBlackError) {
          console.error('Failed to create black player with regular client:', regularBlackError);
        }
      } else {
        console.log('Created black player successfully');
      }
    }
  } catch (error) {
    console.error('Error ensuring players exist:', error);
  }
}

/**
 * Update player statistics after a completed game
 */
async function updatePlayerStats(match) {
  const { supabase } = require('./supabase');
  
  if (!match.result || !match.result.winner) return;
  
  try {
    const winnerColor = match.result.winner; // 'white' or 'black'
    const winnerId = winnerColor === 'white' ? match.players.white.id : match.players.black.id;
    const loserId = winnerColor === 'white' ? match.players.black.id : match.players.white.id;
    
    // Update winner stats
    const { error: winnerError } = await supabase.rpc('increment_win', { user_id: winnerId });
    if (winnerError) console.error('Failed to update winner stats:', winnerError);
    
    // Update loser stats
    const { error: loserError } = await supabase.rpc('increment_loss', { user_id: loserId });
    if (loserError) console.error('Failed to update loser stats:', loserError);
    
    console.log(`Updated player stats - Winner: ${winnerId}, Loser: ${loserId}`);
  } catch (error) {
    console.error('Error updating player statistics:', error);
  }
}

/**
 * Save moves to the database with improved reliability
 */
async function saveMoves(gameId, moveHistory) {
  try {
    if (!moveHistory || moveHistory.length === 0) {
      console.warn(`No move history to save for game ${gameId}`);
      return;
    }

    const { supabase, supabaseAdmin } = require('./supabase');
    console.log(`Saving ${moveHistory.length} moves for game ${gameId}`);
    
    // Get match data for player IDs
    const match = activeMatches.get(gameId);
    if (!match) {
      console.warn(`Match ${gameId} not found in active matches when saving moves`);
    }
    
    // Format moves for database insertion
    const movesData = moveHistory.map((move, index) => {
      // Get the player ID based on color, with safety checks
      let playerId;
      
      if (match && match.players) {
        playerId = move.player === 'white' ? 
          match.players.white.id : 
          match.players.black.id;
      } else {
        // If match is not available, try to extract from move data
        playerId = move.playerId || move.userId || (move.signature ? `player_${move.signature.substring(0, 8)}` : null);
      }
      
      // Ensure required fields have values
      return {
        game_id: gameId,
        move_number: index + 1,
        color: move.player || (index % 2 === 0 ? 'white' : 'black'), // Fallback based on move number
        from_square: move.from || 'unknown',
        to_square: move.to || 'unknown',
        fen_after: move.fen || 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', // Default FEN
        signature: move.signature || 'demo',
        player_id: playerId || `unknown_${index % 2 === 0 ? 'white' : 'black'}`,
        timestamp: move.timestamp || new Date(),
        piece: move.piece || 'unknown',
        promotion: move.promotion || null,
        capture: move.capture || false
      };
    });
    
    // Try to save moves with multiple fallback strategies
    let saveSuccess = false;
    
    // Strategy 1: Use bulk insert with batching if there are a lot of moves
    if (!saveSuccess) {
      try {
        // Use smaller batch size for better reliability
        const BATCH_SIZE = 10;
        
        if (movesData.length > BATCH_SIZE) {
          let batchSuccess = true;
          
          // Break into batches
          for (let i = 0; i < movesData.length; i += BATCH_SIZE) {
            const batch = movesData.slice(i, i + BATCH_SIZE);
            const batchLabel = `${i+1}-${Math.min(i+BATCH_SIZE, movesData.length)}`;
            
            console.log(`Saving moves batch ${batchLabel} of ${movesData.length} moves`);
            
            // Try with admin client first
            const { error: adminError } = await supabaseAdmin.from('moves').insert(batch);
            
            if (adminError) {
              console.error(`Error saving moves batch ${batchLabel} with admin client:`, adminError);
              
              // Try with RPC function as second attempt
              try {
                for (const move of batch) {
                  const { error: rpcError } = await supabase.rpc('insert_move_safely', move);
                  if (rpcError) {
                    console.error(`Error inserting move via RPC:`, rpcError);
                    batchSuccess = false;
                  }
                }
              } catch (rpcErr) {
                console.error('Error using RPC for move insertion:', rpcErr);
                
                // Try with regular client as final fallback
                const { error: regularError } = await supabase.from('moves').insert(batch);
                
                if (regularError) {
                  console.error(`Error saving moves batch ${batchLabel} with regular client:`, regularError);
                  batchSuccess = false;
                }
              }
            }
          }
          
          saveSuccess = batchSuccess;
        } else {
          // Small enough batch to insert all at once
          const { error: adminError } = await supabaseAdmin.from('moves').insert(movesData);
          
          if (!adminError) {
            saveSuccess = true;
            console.log('All moves saved successfully with admin client');
          } else {
            console.error('Error saving moves with admin client:', adminError);
            
            // Try with regular client as fallback
            const { error: regularError } = await supabase.from('moves').insert(movesData);
            
            if (!regularError) {
              saveSuccess = true;
              console.log('All moves saved successfully with regular client');
            } else {
              console.error('Error saving moves with regular client:', regularError);
            }
          }
        }
      } catch (error) {
        console.error('Exception during batch saving of moves:', error);
      }
    }
    
    // Strategy 2: Use one-by-one insertion as last resort
    if (!saveSuccess) {
      console.log('Attempting one-by-one move insertion as fallback');
      let individualSuccess = true;
      
      for (let i = 0; i < movesData.length; i++) {
        const move = movesData[i];
        try {
          const { error } = await supabaseAdmin.from('moves').insert([move]);
          
          if (error) {
            console.error(`Error inserting move ${i+1}:`, error);
            individualSuccess = false;
          }
        } catch (err) {
          console.error(`Exception inserting move ${i+1}:`, err);
          individualSuccess = false;
        }
      }
      
      saveSuccess = individualSuccess;
    }
    
    if (saveSuccess) {
      console.log(`All ${movesData.length} moves saved successfully for game ${gameId}`);
    } else {
      console.warn(`Some moves may not have been saved for game ${gameId}`);
    }
    
    return saveSuccess;
  } catch (error) {
    console.error('Exception while saving moves:', error);
    return false;
  }
}

/**
 * Retrieve game data from the database
 * @param {string} gameId - The ID of the game to retrieve
 * @returns {Promise<Object|null>} - The game data or null if not found
 */
async function retrieveGameFromDatabase(gameId) {
  try {
    const { supabase } = require('./supabase');
    console.log(`Retrieving game ${gameId} from database`);
    
    // Get the game data
    const { data: gameData, error: gameError } = await supabase
      .from('games')
      .select('*')
      .eq('id', gameId)
      .single();
    
    if (gameError || !gameData) {
      console.error('Error retrieving game data:', gameError);
      return null;
    }
    
    // Get the moves for this game
    const { data: movesData, error: movesError } = await supabase
      .from('moves')
      .select('*')
      .eq('game_id', gameId)
      .order('move_number', { ascending: true });
    
    if (movesError) {
      console.error('Error retrieving moves data:', movesError);
      // Return just the game data without moves
      return gameData;
    }
    
    // Add moves to game data
    gameData.moves = movesData.map(move => ({
      from: move.from_square,
      to: move.to_square,
      player: move.color,
      timestamp: move.timestamp,
      signature: move.signature,
      piece: move.piece,
      fen: move.fen_after
    }));
    
    return gameData;
  } catch (error) {
    console.error('Exception retrieving game from database:', error);
    return null;
  }
}

/**
 * Fetch user details from the database
 * @param {string} user1Id - First user's ID
 * @param {string} user2Id - Second user's ID
 * @returns {Promise<[Object, Object]>} - Array containing user details objects
 */
async function fetchUserDetails(user1Id, user2Id) {
  try {
    const { supabase } = require('./supabase');
    
    // Fetch both users in a single query for efficiency
    const { data, error } = await supabase
      .from('users')
      .select('id, username, rating, public_key, wins, losses')
      .in('id', [user1Id, user2Id]);
    
    if (error) {
      console.error('Error fetching user details:', error);
      return [null, null];
    }
    
    // Find each user's details from the results
    const user1Details = data.find(user => user.id === user1Id);
    const user2Details = data.find(user => user.id === user2Id);
    
    return [user1Details || null, user2Details || null];
  } catch (error) {
    console.error('Exception fetching user details:', error);
    return [null, null];
  }
}

/**
 * Generate a unique match ID
 */
function generateMatchId() {
  return Date.now().toString(36) + Math.random().toString(36).substring(2, 5).toUpperCase();
}

module.exports = { setupWebSocket };
