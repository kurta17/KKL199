/**
 * API service for interacting with the backend
 */

import axios from 'axios';

// Authentication API calls
export const authAPI = {
  // Register a new user
  register: async (userData) => {
    try {
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(userData),
      });
      
      return await response.json();
    } catch (error) {
      console.error('Registration error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },

  // Login user
  login: async (credentials) => {
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(credentials),
      });
      
      const result = await response.json();
      
      // If we get an email confirmation error in development mode,
      // offer a bypass option by trying the development endpoint
      if (result.success === false && 
          result.message?.includes('Email not confirmed') && 
          import.meta.env.DEV) {
        console.log('Development mode: Attempting to bypass email confirmation...');
        return authAPI.devForceLogin(credentials);
      }
      
      return result;
    } catch (error) {
      console.error('Login error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },
  
  // Development-only force login that bypasses email confirmation
  // This should NEVER be used in production
  devForceLogin: async (credentials) => {
    // Only available in development mode
    if (!import.meta.env.DEV) {
      return { 
        success: false, 
        message: 'Development bypass not available in production mode' 
      };
    }
    
    try {
      // Try the new bypass auth first if available
      try {
        console.log('Attempting to use bypass auth first...');
        const bypassResponse = await fetch('/api/bypass/login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(credentials),
        });
        
        if (bypassResponse.ok) {
          const bypassResult = await bypassResponse.json();
          if (bypassResult.success) {
            console.warn('⚠️ USING BYPASS AUTH - FOR DEVELOPMENT ONLY ⚠️');
            return bypassResult;
          }
        }
      } catch (bypassError) {
        console.log('Bypass auth not available, falling back to dev force-login');
      }
      
      // Fall back to original dev force-login
      const response = await fetch('/api/dev/force-login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...credentials,
          autoConfirm: true  // Enable auto confirmation for development
        }),
      });
      
      const result = await response.json();
      if (result.dev === true) {
        console.warn('⚠️ USING DEVELOPMENT BYPASS AUTH - NOT FOR PRODUCTION ⚠️');
      }
      return result;
    } catch (error) {
      console.error('Dev force login error:', error);
      return { success: false, message: 'Network error in development login bypass.' };
    }
  },
  
  // Completely bypass Supabase Auth registration
  // This is only for development and should NEVER be used in production
  bypassRegister: async (userData) => {
    // Only available in development mode
    if (!import.meta.env.DEV) {
      return { 
        success: false, 
        message: 'Bypass registration not available in production mode' 
      };
    }
    
    try {
      console.log('🔧 Making bypass registration request to /api/bypass/register');
      
      const response = await fetch('/api/bypass/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(userData),
      });
      
      if (!response.ok) {
        console.error('❌ Bypass API responded with status:', response.status);
        if (response.status === 404) {
          console.error('❌ Endpoint /api/bypass/register not found! Check server configuration.');
          return { success: false, message: 'Registration endpoint not found. Server issue.' };
        }
      }
      
      const result = await response.json();
      if (result.success) {
        console.warn('✅ BYPASS REGISTRATION SUCCESSFUL - FOR DEVELOPMENT ONLY ⚠️');
      } else {
        console.error('❌ Bypass registration error:', result.message);
      }
      return result;
    } catch (error) {
      console.error('❌ Bypass registration network error:', error);
      return { success: false, message: 'Network error in bypass registration.' };
    }
  },

  // Request password reset
  forgotPassword: async (email) => {
    try {
      const response = await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email }),
      });
      
      return await response.json();
    } catch (error) {
      console.error('Password reset request error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },
};

// Game API calls
export const gameAPI = {
  // Get all games for the current user
  getUserGames: async () => {
    try {
      const token = localStorage.getItem('userToken');
      if (!token) {
        return { success: false, message: 'No authentication token found' };
      }

      const response = await fetch('/api/game/games', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      return await response.json();
    } catch (error) {
      console.error('Get games error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },

  // Get a specific game's details
  getGameDetails: async (gameId) => {
    try {
      const token = localStorage.getItem('userToken');
      if (!token) {
        return { success: false, message: 'No authentication token found' };
      }

      const response = await fetch(`/api/game/game/${gameId}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      return await response.json();
    } catch (error) {
      console.error('Get game details error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },

  // Submit a move in a game
  submitMove: async (gameId, move, signature, fen) => {
    try {
      const token = localStorage.getItem('userToken');
      if (!token) {
        return { success: false, message: 'No authentication token found' };
      }

      const response = await fetch('/api/game/move', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          id: gameId,
          move,
          signature,
          fen,
        }),
      });
      
      return await response.json();
    } catch (error) {
      console.error('Submit move error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },

  // Challenge another player
  challengePlayer: async (opponentId) => {
    try {
      const token = localStorage.getItem('userToken');
      if (!token) {
        return { success: false, message: 'No authentication token found' };
      }

      const response = await fetch('/api/game/challenge', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ opponentId }),
      });
      
      return await response.json();
    } catch (error) {
      console.error('Challenge player error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },

  // Resign a game
  resignGame: async (gameId) => {
    try {
      const token = localStorage.getItem('userToken');
      if (!token) {
        return { success: false, message: 'No authentication token found' };
      }

      const response = await fetch(`/api/game/resign/${gameId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      return await response.json();
    } catch (error) {
      console.error('Resign game error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },

  // Offer a draw
  offerDraw: async (gameId) => {
    try {
      const token = localStorage.getItem('userToken');
      if (!token) {
        return { success: false, message: 'No authentication token found' };
      }

      const response = await fetch(`/api/game/offer-draw/${gameId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      return await response.json();
    } catch (error) {
      console.error('Offer draw error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },

  // Respond to a draw offer
  respondToDraw: async (gameId, accept) => {
    try {
      const token = localStorage.getItem('userToken');
      if (!token) {
        return { success: false, message: 'No authentication token found' };
      }

      const response = await fetch(`/api/game/respond-draw/${gameId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ accept }),
      });
      
      return await response.json();
    } catch (error) {
      console.error('Respond to draw error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },

  // Verify game integrity
  verifyGame: async (gameId) => {
    try {
      const token = localStorage.getItem('userToken');
      if (!token) {
        return { success: false, message: 'No authentication token found' };
      }

      const response = await fetch(`/api/game/verify/${gameId}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      return await response.json();
    } catch (error) {
      console.error('Verify game error:', error);
      return { success: false, message: 'Network error. Please try again.' };
    }
  },
};

// Blockchain API calls
const getBlockchainGameHistory = async (gameId) => {
  try {
    const response = await axios.get(`/api/blockchain/games/${gameId}`);
    return response;
  } catch (error) {
    console.error('Error fetching blockchain game history:', error);
    throw error;
  }
};

const getBlockchainHealth = async () => {
  try {
    const response = await axios.get('/api/blockchain/health');
    return response;
  } catch (error) {
    console.error('Error checking blockchain health:', error);
    throw error;
  }
};

// WebSocket connection for live updates
export class GameSocket {
  constructor() {
    this.socket = null;
    this.onMatchHandler = null;
    this.onMoveHandler = null;
    this.onGameOverHandler = null;
    this.onDrawOfferHandler = null;
    this.onErrorHandler = null;
    this.onConnectedHandler = null;
    this.onDisconnectedHandler = null;
    this.onGameStateHandler = null;
  }

  // Connect to WebSocket server with improved stability
  connect() {
    try {
      // Close existing connection if any
      if (this.socket && this.socket.readyState !== WebSocket.CLOSED) {
        this.clearPingPong();
        try {
          this.socket.close();
        } catch (err) {
          console.warn('Error closing existing socket:', err);
        }
      }
      
      // Create new WebSocket connection
      console.log('Creating new WebSocket connection');
      this.socket = new WebSocket('ws://localhost:5000');
      this.pingInterval = null;
      this.pingTimeout = null;

      // Set a connection timeout (5 seconds)
      const connectionTimeout = setTimeout(() => {
        if (this.socket && this.socket.readyState !== WebSocket.OPEN) {
          console.error('WebSocket connection timeout');
          this.socket.close();
          if (this.onErrorHandler) this.onErrorHandler({ message: 'Connection timeout' });
        }
      }, 5000);

      this.socket.onopen = () => {
        console.log('WebSocket connected successfully');
        clearTimeout(connectionTimeout);
        
        const userId = localStorage.getItem('userId');
        if (userId) {
          console.log(`Authenticating user: ${userId}`);
          this.authenticate(userId);
        } else {
          console.warn('No user ID found in localStorage');
        }
        
        // Start ping/pong for connection monitoring
        this.startPingPong();
        
        if (this.onConnectedHandler) this.onConnectedHandler();
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Reset ping timeout whenever we receive any message
          this.resetPingTimeout();
          
          switch (data.type) {
            case 'match':
              if (this.onMatchHandler) this.onMatchHandler(data);
              break;
            case 'opponentMove':
              if (this.onMoveHandler) this.onMoveHandler(data);
              break;
            case 'gameOver':
              if (this.onGameOverHandler) this.onGameOverHandler(data);
              break;
            case 'drawOffer':
              if (this.onDrawOfferHandler) this.onDrawOfferHandler(data);
              break;
            case 'gameState':
              if (this.onGameStateHandler) this.onGameStateHandler(data);
              break;
            case 'error':
              if (this.onErrorHandler) this.onErrorHandler(data);
              break;
            case 'pong':
              // Received pong response, connection is alive
              break;
            default:
              console.log('Received message:', data);
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      this.socket.onclose = () => {
        console.log('WebSocket disconnected');
        this.clearPingPong();
        if (this.onDisconnectedHandler) this.onDisconnectedHandler();
      };

      this.socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.clearPingPong();
        if (this.onErrorHandler) this.onErrorHandler({ message: 'Connection error' });
      };

    } catch (error) {
      console.error('WebSocket connection error:', error);
    }
  }

  // Close the connection
  disconnect() {
    if (this.socket) {
      this.clearPingPong();
      this.socket.close();
      this.socket = null;
    }
  }
  
  // Start ping/pong heartbeat
  startPingPong() {
    this.clearPingPong();
    
    // Send a ping every 15 seconds
    this.pingInterval = setInterval(() => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ type: 'ping' }));
        
        // Set a timeout to detect if we don't get a pong back
        this.resetPingTimeout();
      }
    }, 15000);
  }
  
  // Reset ping timeout
  resetPingTimeout() {
    // Clear existing timeout
    if (this.pingTimeout) {
      clearTimeout(this.pingTimeout);
    }
    
    // Set new timeout - if we don't hear back within 10 seconds, consider connection dead
    this.pingTimeout = setTimeout(() => {
      console.log('Ping timeout - connection appears dead');
      if (this.socket) {
        this.socket.close();
      }
    }, 10000);
  }
  
  // Clear all ping/pong timers
  clearPingPong() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
    
    if (this.pingTimeout) {
      clearTimeout(this.pingTimeout);
      this.pingTimeout = null;
    }
  }

  // Authenticate with the WebSocket server
  authenticate(userId) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({
        type: 'authenticate',
        userId,
      }));
    }
  }

  // Join matchmaking queue
  joinQueue() {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({
        type: 'joinQueue',
      }));
    }
  }

  // Send a move
  sendMove(matchId, move, signature) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({
        type: 'move',
        matchId,
        move,
        signature,
      }));
    }
  }

  // Resign from a game
  resign(matchId) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({
        type: 'resign',
        matchId,
      }));
    }
  }

  // Offer a draw
  offerDraw(matchId) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({
        type: 'drawOffer',
        matchId,
      }));
    }
  }

  // Respond to a draw offer
  respondToDrawOffer(matchId, accepted) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({
        type: 'drawResponse',
        matchId,
        accepted,
      }));
    }
  }

  // Request current game state (useful after reconnection)
  requestGameState(matchId) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN && matchId) {
      this.socket.send(JSON.stringify({
        type: 'getGameState',
        matchId
      }));
      console.log(`Requested game state for match: ${matchId}`);
      return true;
    }
    console.warn(`Cannot request game state: socket not ready or matchId missing`);
    return false;
  }

  // Set event handlers
  onMatch(handler) {
    this.onMatchHandler = handler;
  }

  onMove(handler) {
    this.onMoveHandler = handler;
  }

  onGameOver(handler) {
    this.onGameOverHandler = handler;
  }

  onDrawOffer(handler) {
    this.onDrawOfferHandler = handler;
  }
  
  onGameState(handler) {
    this.onGameStateHandler = handler;
  }

  onError(handler) {
    this.onErrorHandler = handler;
  }
  
  onConnected(handler) {
    this.onConnectedHandler = handler;
  }
  
  onDisconnected(handler) {
    this.onDisconnectedHandler = handler;
  }
}

// Export a default object with all API methods
export default {
  ...authAPI,
  getBlockchainGameHistory,
  getBlockchainHealth
};
