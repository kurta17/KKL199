const { v4: uuidv4 } = require('uuid');
const supabase = require('../utils/supabase');
const { verifySignature, createHash, buildMerkleTree, verifyProof } = require('../utils/blockchain');

/**
 * Challenge another player to a game
 */
async function challengePlayer(req, res) {
  try {
    const { opponentId } = req.body;
    const userId = req.user.id;
    
    // Validate input
    if (!opponentId) {
      return res.status(400).json({ success: false, message: 'Please provide an opponent ID' });
    }
    
    // Make sure you can't challenge yourself
    if (opponentId === userId) {
      return res.status(400).json({ success: false, message: 'You cannot challenge yourself' });
    }
    
    // Check if opponent exists
    const { data: opponent, error: opponentError } = await supabase
      .from('users')
      .select('id, username')
      .eq('id', opponentId)
      .single();
      
    if (opponentError || !opponent) {
      return res.status(404).json({ success: false, message: 'Opponent not found' });
    }
    
    // Create a new game
    const gameId = uuidv4();
    const { error: gameError } = await supabase
      .from('games')
      .insert([
        {
          id: gameId,
          white_player_id: userId,
          black_player_id: opponentId,
          status: 'pending',
          created_at: new Date()
        }
      ]);
      
    if (gameError) {
      console.error('Error creating game:', gameError);
      return res.status(500).json({ success: false, message: 'Error creating game' });
    }
    
    // Return success
    res.status(201).json({
      success: true,
      message: 'Challenge sent successfully',
      game: {
        id: gameId,
        opponent: opponent.username,
        status: 'pending'
      }
    });
    
  } catch (error) {
    console.error('Challenge player error:', error);
    res.status(500).json({ success: false, message: 'Server error creating challenge' });
  }
}

/**
 * Get all games for the current user
 */
async function getUserGames(req, res) {
  try {
    const userId = req.user.id;
    
    // Get games where user is either white or black
    const { data: games, error } = await supabase
      .from('games')
      .select(`
        id, 
        status, 
        created_at, 
        result,
        white_player:white_player_id(id, username, rating),
        black_player:black_player_id(id, username, rating)
      `)
      .or(`white_player_id.eq.${userId},black_player_id.eq.${userId}`)
      .order('created_at', { ascending: false });
      
    if (error) {
      console.error('Error fetching games:', error);
      return res.status(500).json({ success: false, message: 'Error fetching games' });
    }
    
    // Return success
    res.status(200).json({
      success: true,
      games
    });
    
  } catch (error) {
    console.error('Get user games error:', error);
    res.status(500).json({ success: false, message: 'Server error fetching games' });
  }
}

/**
 * Get details of a specific game
 */
async function getGameDetails(req, res) {
  try {
    const { id: gameId } = req.params;
    const userId = req.user.id;
    
    // Get game details
    const { data: game, error } = await supabase
      .from('games')
      .select(`
        id, 
        status, 
        created_at,
        result,
        white_player:white_player_id(id, username, rating),
        black_player:black_player_id(id, username, rating)
      `)
      .eq('id', gameId)
      .single();
      
    if (error || !game) {
      return res.status(404).json({ success: false, message: 'Game not found' });
    }
    
    // Check if user is part of this game
    if (game.white_player.id !== userId && game.black_player.id !== userId) {
      return res.status(403).json({ success: false, message: 'You are not a participant in this game' });
    }
    
    // Get moves
    const { data: moves, error: movesError } = await supabase
      .from('moves')
      .select('*')
      .eq('game_id', gameId)
      .order('move_number', { ascending: true });
      
    if (movesError) {
      console.error('Error fetching moves:', movesError);
      return res.status(500).json({ success: false, message: 'Error fetching game moves' });
    }
    
    // Add moves to game object
    game.moves = moves || [];
    
    // Return success
    res.status(200).json({
      success: true,
      game
    });
    
  } catch (error) {
    console.error('Get game details error:', error);
    res.status(500).json({ success: false, message: 'Server error fetching game details' });
  }
}

/**
 * Submit a move
 */
async function submitMove(req, res) {
  try {
    const { move, signature, fen } = req.body;
    const { id: gameId } = req.body;
    const userId = req.user.id;
    
    // Validate input
    if (!move || !signature || !fen || !gameId) {
      return res.status(400).json({ 
        success: false, 
        message: 'Please provide move, signature, FEN, and game ID' 
      });
    }
    
    // Get game details
    const { data: game, error: gameError } = await supabase
      .from('games')
      .select('*')
      .eq('id', gameId)
      .single();
      
    if (gameError || !game) {
      return res.status(404).json({ success: false, message: 'Game not found' });
    }
    
    // Check if game is active
    if (game.status !== 'active') {
      return res.status(400).json({ success: false, message: 'Game is not active' });
    }
    
    // Check if user is part of this game
    if (game.white_player_id !== userId && game.black_player_id !== userId) {
      return res.status(403).json({ success: false, message: 'You are not a participant in this game' });
    }
    
    // Determine if user is white or black
    const isWhite = game.white_player_id === userId;
    
    // Get latest move to determine whose turn it is
    const { data: latestMove, error: moveError } = await supabase
      .from('moves')
      .select('*')
      .eq('game_id', gameId)
      .order('move_number', { ascending: false })
      .limit(1)
      .single();
      
    // Determine if it's user's turn
    let isUserTurn = false;
    let moveNumber = 1;
    
    if (moveError && moveError.code === 'PGRST116') {
      // No moves yet, white goes first
      isUserTurn = isWhite;
    } else if (!moveError) {
      isUserTurn = (isWhite && latestMove.color === 'black') || (!isWhite && latestMove.color === 'white');
      moveNumber = latestMove.move_number + 1;
    } else {
      console.error('Error fetching latest move:', moveError);
      return res.status(500).json({ success: false, message: 'Error checking game state' });
    }
    
    if (!isUserTurn) {
      return res.status(400).json({ success: false, message: 'Not your turn' });
    }
    
    // Get user's public key
    const { data: user, error: userError } = await supabase
      .from('users')
      .select('public_key')
      .eq('id', userId)
      .single();
      
    if (userError || !user) {
      console.error('Error fetching user public key:', userError);
      return res.status(500).json({ success: false, message: 'Error fetching user data' });
    }
    
    // Verify signature
    const moveData = JSON.stringify({ from: move.from, to: move.to, fen });
    const isValidSignature = verifySignature(moveData, signature, user.public_key);
    
    if (!isValidSignature) {
      return res.status(400).json({ success: false, message: 'Invalid signature' });
    }
    
    // Insert move into database
    const { error: insertError } = await supabase
      .from('moves')
      .insert([
        {
          game_id: gameId,
          move_number: moveNumber,
          color: isWhite ? 'white' : 'black',
          from_square: move.from,
          to_square: move.to,
          fen_after: fen,
          signature,
          player_id: userId,
          timestamp: new Date()
        }
      ]);
      
    if (insertError) {
      console.error('Error inserting move:', insertError);
      return res.status(500).json({ success: false, message: 'Error recording move' });
    }
    
    // Update game status if necessary (e.g., check for checkmate, stalemate)
    // This would require chess logic which we'll mock for now
    
    // Return success
    res.status(200).json({
      success: true,
      message: 'Move submitted successfully',
      moveNumber,
      fen
    });
    
  } catch (error) {
    console.error('Submit move error:', error);
    res.status(500).json({ success: false, message: 'Server error submitting move' });
  }
}

/**
 * Verify game integrity using Merkle tree
 */
async function verifyGame(req, res) {
  try {
    const { id: gameId } = req.params;
    
    // Get game details
    const { data: game, error: gameError } = await supabase
      .from('games')
      .select('id, status')
      .eq('id', gameId)
      .single();
      
    if (gameError || !game) {
      return res.status(404).json({ success: false, message: 'Game not found' });
    }
    
    // Get all moves
    const { data: moves, error: movesError } = await supabase
      .from('moves')
      .select('*')
      .eq('game_id', gameId)
      .order('move_number', { ascending: true });
      
    if (movesError) {
      console.error('Error fetching moves:', movesError);
      return res.status(500).json({ success: false, message: 'Error fetching game moves' });
    }
    
    if (!moves || moves.length === 0) {
      return res.status(400).json({ success: false, message: 'No moves to verify' });
    }
    
    // Build Merkle tree from moves
    const moveData = moves.map(move => ({
      gameId: move.game_id,
      moveNumber: move.move_number,
      color: move.color,
      fromSquare: move.from_square,
      toSquare: move.to_square,
      playerId: move.player_id,
      signature: move.signature
    }));
    
    const { tree, root } = buildMerkleTree(moveData);
    
    // Get stored root if available
    const { data: storedRoot, error: rootError } = await supabase
      .from('game_verifications')
      .select('merkle_root')
      .eq('game_id', gameId)
      .single();
    
    let isVerified = false;
    
    if (!rootError && storedRoot) {
      // Compare with stored root
      isVerified = storedRoot.merkle_root === root;
    } else {
      // Store new root
      const { error: insertError } = await supabase
        .from('game_verifications')
        .insert([
          {
            game_id: gameId,
            merkle_root: root,
            verified_at: new Date()
          }
        ]);
        
      if (insertError) {
        console.error('Error storing merkle root:', insertError);
      } else {
        isVerified = true;
      }
    }
    
    // Return verification result
    res.status(200).json({
      success: true,
      isVerified,
      merkleRoot: root,
      movesCount: moves.length
    });
    
  } catch (error) {
    console.error('Verify game error:', error);
    res.status(500).json({ success: false, message: 'Server error verifying game' });
  }
}

/**
 * Resign a game
 */
async function resignGame(req, res) {
  try {
    const { id: gameId } = req.params;
    const userId = req.user.id;
    
    // Get game details
    const { data: game, error: gameError } = await supabase
      .from('games')
      .select('*')
      .eq('id', gameId)
      .single();
      
    if (gameError || !game) {
      return res.status(404).json({ success: false, message: 'Game not found' });
    }
    
    // Check if user is part of this game
    if (game.white_player_id !== userId && game.black_player_id !== userId) {
      return res.status(403).json({ success: false, message: 'You are not a participant in this game' });
    }
    
    // Check if game is active
    if (game.status !== 'active') {
      return res.status(400).json({ success: false, message: 'Game is not active' });
    }
    
    // Determine winner
    const winner = game.white_player_id === userId ? 'black' : 'white';
    
    // Update game status
    const { error: updateError } = await supabase
      .from('games')
      .update({
        status: 'completed',
        result: {
          winner,
          reason: 'resignation'
        },
        completed_at: new Date()
      })
      .eq('id', gameId);
      
    if (updateError) {
      console.error('Error updating game status:', updateError);
      return res.status(500).json({ success: false, message: 'Error updating game' });
    }
    
    // Return success
    res.status(200).json({
      success: true,
      message: 'Game resigned successfully',
      winner
    });
    
  } catch (error) {
    console.error('Resign game error:', error);
    res.status(500).json({ success: false, message: 'Server error resigning game' });
  }
}

/**
 * Offer a draw
 */
async function offerDraw(req, res) {
  try {
    const { id: gameId } = req.params;
    const userId = req.user.id;
    
    // Get game details
    const { data: game, error: gameError } = await supabase
      .from('games')
      .select('*')
      .eq('id', gameId)
      .single();
      
    if (gameError || !game) {
      return res.status(404).json({ success: false, message: 'Game not found' });
    }
    
    // Check if user is part of this game
    if (game.white_player_id !== userId && game.black_player_id !== userId) {
      return res.status(403).json({ success: false, message: 'You are not a participant in this game' });
    }
    
    // Check if game is active
    if (game.status !== 'active') {
      return res.status(400).json({ success: false, message: 'Game is not active' });
    }
    
    // Update game with draw offer
    const { error: updateError } = await supabase
      .from('games')
      .update({
        draw_offered_by: userId,
        draw_offered_at: new Date()
      })
      .eq('id', gameId);
      
    if (updateError) {
      console.error('Error updating draw offer:', updateError);
      return res.status(500).json({ success: false, message: 'Error recording draw offer' });
    }
    
    // Return success
    res.status(200).json({
      success: true,
      message: 'Draw offered successfully'
    });
    
  } catch (error) {
    console.error('Offer draw error:', error);
    res.status(500).json({ success: false, message: 'Server error offering draw' });
  }
}

/**
 * Respond to a draw offer
 */
async function respondDraw(req, res) {
  try {
    const { id: gameId } = req.params;
    const { accept } = req.body;
    const userId = req.user.id;
    
    // Validate input
    if (accept === undefined) {
      return res.status(400).json({ success: false, message: 'Please specify whether to accept the draw' });
    }
    
    // Get game details
    const { data: game, error: gameError } = await supabase
      .from('games')
      .select('*')
      .eq('id', gameId)
      .single();
      
    if (gameError || !game) {
      return res.status(404).json({ success: false, message: 'Game not found' });
    }
    
    // Check if user is part of this game
    if (game.white_player_id !== userId && game.black_player_id !== userId) {
      return res.status(403).json({ success: false, message: 'You are not a participant in this game' });
    }
    
    // Check if there's an active draw offer
    if (!game.draw_offered_by) {
      return res.status(400).json({ success: false, message: 'No active draw offer' });
    }
    
    // Check if user is not the one who offered the draw
    if (game.draw_offered_by === userId) {
      return res.status(400).json({ success: false, message: 'You cannot respond to your own draw offer' });
    }
    
    if (accept) {
      // Accept draw - update game status
      const { error: updateError } = await supabase
        .from('games')
        .update({
          status: 'completed',
          result: {
            winner: null,
            reason: 'draw_agreement'
          },
          completed_at: new Date()
        })
        .eq('id', gameId);
        
      if (updateError) {
        console.error('Error accepting draw:', updateError);
        return res.status(500).json({ success: false, message: 'Error accepting draw' });
      }
      
      res.status(200).json({
        success: true,
        message: 'Draw accepted'
      });
    } else {
      // Decline draw - just clear the offer
      const { error: updateError } = await supabase
        .from('games')
        .update({
          draw_offered_by: null,
          draw_offered_at: null
        })
        .eq('id', gameId);
        
      if (updateError) {
        console.error('Error declining draw:', updateError);
        return res.status(500).json({ success: false, message: 'Error declining draw' });
      }
      
      res.status(200).json({
        success: true,
        message: 'Draw declined'
      });
    }
    
  } catch (error) {
    console.error('Respond to draw error:', error);
    res.status(500).json({ success: false, message: 'Server error responding to draw' });
  }
}

module.exports = {
  challengePlayer,
  getUserGames,
  getGameDetails,
  submitMove,
  verifyGame,
  resignGame,
  offerDraw,
  respondDraw
};
