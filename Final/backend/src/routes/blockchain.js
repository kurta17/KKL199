/**
 * Blockchain routes for interacting with the ChessChain blockchain
 */
const express = require('express');
const { checkBlockchainHealth, getGameHistory } = require('../services/blockchain-bridge');
const router = express.Router();

/**
 * GET /api/blockchain/health
 * Check the health status of the blockchain node
 */
router.get('/health', async (req, res) => {
  try {
    const health = await checkBlockchainHealth();
    res.json(health);
  } catch (err) {
    console.error('Error checking blockchain health:', err);
    res.status(503).json({
      status: 'error',
      message: 'Blockchain node is unavailable',
      error: err.message
    });
  }
});

/**
 * GET /api/blockchain/games/:gameId
 * Get the move history for a game from the blockchain
 */
router.get('/games/:gameId', async (req, res) => {
  const { gameId } = req.params;
  
  if (!gameId) {
    return res.status(400).json({
      status: 'error',
      message: 'Game ID is required'
    });
  }
  
  try {
    const moves = await getGameHistory(gameId);
    res.json({
      game_id: gameId,
      moves,
      verified: true
    });
  } catch (err) {
    console.error(`Error fetching game history for ${gameId}:`, err);
    res.status(500).json({
      status: 'error',
      message: 'Failed to fetch game history',
      error: err.message
    });
  }
});

module.exports = router;
