/**
 * Bridge between Node.js backend and Python blockchain implementation
 * This module provides functions to interact with the ChessChain blockchain
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const axios = require('axios');

// Configuration - can be moved to env variables later
const BLOCKCHAIN_API_PORT = process.env.BLOCKCHAIN_API_PORT || 8080;
const BLOCKCHAIN_API_URL = process.env.BLOCKCHAIN_API_URL || `http://localhost:${BLOCKCHAIN_API_PORT}`;
const BLOCKCHAIN_PATH = process.env.BLOCKCHAIN_PATH || path.join(__dirname, '../../../ChessChain');

// Track if blockchain node is running
let isBlockchainRunning = false;
let blockchainProcess = null;

/**
 * Start the blockchain node as a subprocess
 */
async function startBlockchainNode() {
  // Don't start if already running
  if (isBlockchainRunning) {
    console.log('Blockchain node is already running');
    return true;
  }

  console.log(`Starting blockchain node from: ${BLOCKCHAIN_PATH}`);
  
  try {
    // Check if the directory exists
    if (!fs.existsSync(BLOCKCHAIN_PATH)) {
      throw new Error(`Blockchain directory not found: ${BLOCKCHAIN_PATH}`);
    }

    // Spawn Python process
    blockchainProcess = spawn('python', [
      path.join(BLOCKCHAIN_PATH, 'main.py'), 
      '--api', 
      `--api-port=${BLOCKCHAIN_API_PORT}`,
      `--port=8000`  // Blockchain node port (different from API port)
    ], {
      cwd: BLOCKCHAIN_PATH,
      stdio: ['pipe', 'pipe', 'pipe'] // stdin, stdout, stderr
    });

    // Handle process output
    blockchainProcess.stdout.on('data', (data) => {
      console.log(`Blockchain: ${data.toString().trim()}`);
      // If we see the API is ready, mark as running
      if (data.toString().includes('Blockchain API running on port')) {
        isBlockchainRunning = true;
      }
    });

    blockchainProcess.stderr.on('data', (data) => {
      console.error(`Blockchain Error: ${data.toString().trim()}`);
    });

    blockchainProcess.on('close', (code) => {
      console.log(`Blockchain process exited with code ${code}`);
      isBlockchainRunning = false;
      blockchainProcess = null;
    });

    // Wait for blockchain to start
    return new Promise((resolve) => {
      let checkCount = 0;
      const checkInterval = setInterval(async () => {
        checkCount++;
        // Check if the API is responding
        try {
          const response = await axios.get(`${BLOCKCHAIN_API_URL}/health`);
          if (response.status === 200) {
            console.log('Blockchain API is ready!');
            clearInterval(checkInterval);
            isBlockchainRunning = true;
            resolve(true);
            return;
          }
        } catch (error) {
          // Not ready yet, ignore error
        }

        // Timeout after 30 attempts (30 seconds)
        if (checkCount > 30) {
          console.error('Timed out waiting for blockchain to start');
          clearInterval(checkInterval);
          resolve(false);
        }
      }, 1000);
    });
  } catch (error) {
    console.error('Error starting blockchain node:', error);
    return false;
  }
}

/**
 * Stop the blockchain node
 */
function stopBlockchainNode() {
  if (blockchainProcess) {
    console.log('Stopping blockchain node');
    blockchainProcess.kill();
    isBlockchainRunning = false;
    blockchainProcess = null;
    return true;
  }
  return false;
}

/**
 * Submit a move to the blockchain
 * @param {Object} params - The move parameters
 * @param {Object} params.moveData - The move data
 * @param {string} params.signature - The base64 signature of the move
 * @param {string} params.publicKey - The player's base64 public key 
 */
async function submitMove({ moveData, signature, publicKey }) {
  try {
    if (!isBlockchainRunning) {
      await startBlockchainNode();
    }
    
    // Format the move data for the blockchain API
    const blockchainMoveData = {
      game_id: moveData.gameId,
      move_number: moveData.moveNumber,
      from_square: moveData.fromSquare,
      to_square: moveData.toSquare,
      piece: moveData.piece,
      promotion: moveData.promotion,
      player_public_key: publicKey,
      signature: signature
    };
    
    // Log submission (exclude full signature for security)
    console.log('Submitting move to blockchain:', {
      ...blockchainMoveData,
      signature: signature.substring(0, 10) + '...',
      player_public_key: publicKey.substring(0, 10) + '...'
    });
    
    const response = await axios.post(
      `${BLOCKCHAIN_API_URL}/moves`, 
      blockchainMoveData,
      { headers: { 'Content-Type': 'application/json' } }
    );
    
    return response.data;
  } catch (error) {
    console.error('Error submitting move to blockchain:', error.response?.data || error.message);
    throw new Error(`Failed to submit move to blockchain: ${error.message}`);
  }
}

/**
 * Verify a move's signature
 * @param {Object} moveData - The move data
 * @param {string} signature - The signature of the move
 * @param {string} publicKey - The player's public key
 * @returns {Promise<boolean>} - True if the signature is valid, false otherwise
 */
async function verifyMoveSignature(moveData, signature, publicKey) {
  if (!signature || !publicKey) {
    console.warn('Missing signature or public key for verification');
    // When in development, allow unsigned moves
    return process.env.NODE_ENV !== 'production';
  }
  
  try {
    if (!isBlockchainRunning) {
      await startBlockchainNode();
    }
    
    const response = await axios.post(`${BLOCKCHAIN_API_URL}/verify`, {
      move_data: moveData,  // The API expects snake_case
      signature: signature,
      public_key: publicKey
    });
    
    return response.data.valid;
  } catch (error) {
    console.error('Error verifying move signature:', error.response?.data || error.message);
    
    // In case of API error, we'll be permissive in development
    if (process.env.NODE_ENV !== 'production') {
      console.warn('Allowing move despite verification error (development mode)');
      return true;
    }
    
    return false;
  }
}

/**
 * Get the game history from the blockchain
 * @param {string} gameId - The ID of the game
 */
async function getGameHistory(gameId) {
  try {
    if (!isBlockchainRunning) {
      await startBlockchainNode();
    }
    
    const response = await axios.get(`${BLOCKCHAIN_API_URL}/games/${gameId}`);
    return response.data;
  } catch (error) {
    console.error('Error fetching game history from blockchain:', error);
    throw new Error('Failed to fetch game history');
  }
}

/**
 * Check if the blockchain node is running
 */
async function isBlockchainNodeRunning() {
  if (isBlockchainRunning && blockchainProcess) {
    try {
      const response = await axios.get(`${BLOCKCHAIN_API_URL}/health`);
      return response.status === 200;
    } catch (error) {
      isBlockchainRunning = false;
      return false;
    }
  }
  return false;
}

module.exports = {
  startBlockchainNode,
  stopBlockchainNode,
  submitMove,
  verifyMoveSignature,
  getGameHistory,
  isBlockchainNodeRunning
};
