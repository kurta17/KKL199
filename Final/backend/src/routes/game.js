const express = require('express');
const router = express.Router();
const gameController = require('../controllers/game');
const auth = require('../middleware/auth');

// Apply authentication middleware to all game routes
router.use(auth);

// Create a new game (challenge player)
router.post('/challenge', gameController.challengePlayer);

// Get all games for current user
router.get('/games', gameController.getUserGames);

// Get specific game details
router.get('/game/:id', gameController.getGameDetails);

// Submit a move
router.post('/move', gameController.submitMove);

// Verify game integrity
router.get('/verify/:id', gameController.verifyGame);

// Resign game
router.post('/resign/:id', gameController.resignGame);

// Offer draw
router.post('/offer-draw/:id', gameController.offerDraw);

// Respond to draw offer
router.post('/respond-draw/:id', gameController.respondDraw);

module.exports = router;
