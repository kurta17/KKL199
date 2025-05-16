import React, { useState, useEffect, useRef } from 'react';
import { Chess } from 'chess.js';
import { Chessboard } from 'react-chessboard';
import { ethers } from 'ethers';
import { useNavigate } from 'react-router-dom';
import { GameSocket } from './services/api';

function Game() {
  const [chess] = useState(new Chess());
  const [fen, setFen] = useState(chess.fen());
  const [moveHistory, setMoveHistory] = useState([]);
  const [opponent, setOpponent] = useState(null);
  const [isMatched, setIsMatched] = useState(false);
  const [hasAgreed, setHasAgreed] = useState(false);
  const [color, setColor] = useState('white');
  const [gameId, setGameId] = useState(null);
  const [isMyTurn, setIsMyTurn] = useState(true);
  const [gameStatus, setGameStatus] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [drawOffered, setDrawOffered] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('connecting'); // 'connected', 'connecting', 'disconnected'
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  const socketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const navigate = useNavigate();

  // Function to connect websocket with improved stability
  const connectWebSocket = () => {
    // Clear any existing timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    setConnectionStatus('connecting');
    console.log('Connecting to WebSocket server...');

    // Clean up existing socket if any
    if (socketRef.current) {
      try {
        socketRef.current.disconnect();
      } catch (err) {
        console.log('Error disconnecting previous socket:', err);
      }
    }

    // Initialize and connect WebSocket
    const socket = new GameSocket();
    socketRef.current = socket;

    // Set up event handlers
    socket.onMatch((data) => {
      console.log('Match created! Data:', JSON.stringify(data));
      setOpponent(data.opponent);
      setIsMatched(true);
      
      // Set player color immediately and store it
      const playerColor = data.color;
      setColor(playerColor);
      localStorage.setItem('chessPlayerColor', playerColor);
      console.log(`Player assigned color: ${playerColor}`);
      
      setGameId(data.matchId);
      localStorage.setItem('currentGameId', data.matchId);
      
      // Set turn based on color - white moves first
      setIsMyTurn(playerColor === 'white');
    });

    // Add connection status handlers
    socket.onConnected(() => {
      console.log('WebSocket connected');
      setConnectionStatus('connected');
      setReconnectAttempts(0);
    });

    socket.onDisconnected(() => {
      console.log('WebSocket disconnected');
      setConnectionStatus('disconnected');

      // Try to reconnect with exponential backoff
      const delay = Math.min(1000 * (2 ** reconnectAttempts), 30000); // Max 30 seconds
      console.log(`Attempting to reconnect in ${delay}ms`);

      reconnectTimeoutRef.current = setTimeout(() => {
        setReconnectAttempts(prev => prev + 1);
        connectWebSocket();
      }, delay);
    });

    socket.onMove((data) => {
      try {
        // Save current state before applying opponent's move
        const prevFen = chess.fen();
        const prevHistory = chess.history();
        
        // Apply opponent's move
        const move = { 
          from: data.move.from, 
          to: data.move.to,
          promotion: data.move.promotion 
        };
        
        // Try to make the move
        const moveResult = chess.move(move);
        
        if (!moveResult) {
          console.error('Invalid move received from opponent:', move);
          
          // We're out of sync - request full game state to recover
          console.log('Game state inconsistent - requesting full state from server');
          const gameIdToUse = data.matchId || gameId;
          if (gameIdToUse && socketRef.current) {
            socketRef.current.requestGameState(gameIdToUse);
            setErrorMessage('Synchronizing game state...');
          }
          return;
        }
        
        // Get new state after applying move
        const newFen = chess.fen();
        const newHistoryItem = chess.history()[chess.history().length - 1];
        
        console.log(`Opponent moved: ${move.from} to ${move.to} (${newHistoryItem})`);
        
        // If server provided FEN, validate it against our calculated FEN
        if (data.move.fen && data.move.fen !== newFen) {
          console.warn('Server FEN differs from local FEN after move - using server FEN');
          try {
            chess.load(data.move.fen);
            setFen(data.move.fen);
          } catch (fenErr) {
            console.error('Error loading FEN from server:', fenErr);
            setFen(newFen);
          }
        } else {
          // Use our calculated FEN
          setFen(newFen);
        }
        
        // Update move history
        setMoveHistory(prevHistory => [...prevHistory, newHistoryItem]);
        
        // It's now my turn after opponent's move
        setIsMyTurn(true);
        
        // Save game ID to localStorage if not already saved
        if (data.matchId && data.matchId !== localStorage.getItem('currentGameId')) {
          localStorage.setItem('currentGameId', data.matchId);
          console.log('Updated game ID in localStorage:', data.matchId);
          if (!gameId) setGameId(data.matchId);
        }
      } catch (error) {
        console.error('Error processing opponent move:', error);
        
        // Request current game state to recover
        if (gameId && socketRef.current) {
          console.log('Requesting game state recovery after move error');
          socketRef.current.requestGameState(gameId);
          setErrorMessage('Synchronizing after error...');
        } else {
          setErrorMessage('Error processing opponent move. Game state may be inconsistent.');
        }
      }
    });

    socket.onGameOver((data) => {
      console.log('Game over received:', JSON.stringify(data));
      
      // Make sure the result is properly associated with the current player's perspective
      const gameResult = {
        winner: data.result.winner,
        reason: data.result.reason,
        perspective: color // Store player's color to contextualize the result
      };
      
      setGameStatus(gameResult);
      
      // Stop allowing moves
      setIsMyTurn(false);
    });

    socket.onDrawOffer(() => {
      setDrawOffered(true);
    });
    
    socket.onGameState((data) => {
      console.log('Received game state:', JSON.stringify(data));
      
      // Update local game state with received data
      if (data.playerColor) {
        // Use this immediately, don't queue it for next render
        // This ensures board orientation is consistent before any moves
        const playerColor = data.playerColor;
        setColor(playerColor);
        console.log('Setting player color to:', playerColor);
      }
      
      if (data.opponent) {
        // Ensure opponent has standard properties even if some are missing
        setOpponent({
          id: data.opponent.id,
          username: data.opponent.username || `Player ${data.opponent.id.substring(0, 8)}`,
          rating: data.opponent.rating || 1200,
          wins: data.opponent.wins || 0,
          losses: data.opponent.losses || 0
        });
        setIsMatched(true);
      }
      
      if (data.state) {
        // Reset chess instance to initial state
        chess.reset();
        
        const state = data.state;
        
        // Apply all moves from history
        if (state.moveHistory && state.moveHistory.length > 0) {
          try {
            // Reset move history
            setMoveHistory([]);
            
            // Apply each move to get to current state
            state.moveHistory.forEach((historyMove, index) => {
              if (historyMove.from && historyMove.to) {
                // Apply this move to the chess instance
                const moveResult = chess.move({
                  from: historyMove.from,
                  to: historyMove.to,
                  promotion: historyMove.promotion
                });
                
                if (moveResult) {
                  // Update move history
                  setMoveHistory(prev => [...prev, chess.history()[index]]);
                }
              }
            });
            
            // Update FEN after all moves are applied
            setFen(chess.fen());
            
            // Determine if it's the player's turn
            const isPlayerTurn = (chess.history().length % 2 === 0 && data.playerColor === 'white') || 
                                 (chess.history().length % 2 === 1 && data.playerColor === 'black');
            setIsMyTurn(isPlayerTurn);
          } catch (error) {
            console.error('Error reconstructing game from move history:', error);
            setErrorMessage('Failed to reconstruct game state. Please refresh the page.');
          }
        }
        
        // If we have a FEN string in the last move, use that directly
        if (state.lastMove && state.lastMove.fen) {
          try {
            chess.load(state.lastMove.fen);
            setFen(state.lastMove.fen);
          } catch (error) {
            console.error('Error loading FEN from last move:', error);
          }
        }
        
        // Update game status if completed
        if (state.status === 'completed' && state.result) {
          setGameStatus({
            winner: state.result.winner,
            reason: state.result.reason,
            perspective: data.playerColor
          });
          setIsMyTurn(false);
        }
        
        // Update draw offer status
        setDrawOffered(!!state.drawOffer);
      }
      
      // Clear reconnection message
      setErrorMessage('Game state synchronized successfully');
      setTimeout(() => setErrorMessage(''), 3000);
    });

    socket.onError((data) => {
      setErrorMessage(data.message);
      setTimeout(() => setErrorMessage(''), 5000);
    });

    // Connect to server
    socket.connect();

    // Join matchmaking queue after connection is established
    const queueTimeout = setTimeout(() => {
      if (socket && socket.socket && socket.socket.readyState === WebSocket.OPEN) {
        console.log('Joining matchmaking queue');
        socket.joinQueue();
      } else {
        console.log('Not connected yet, delaying queue join');
        // Try again in a second if connection isn't ready
        setTimeout(() => {
          if (socket && socket.socket && socket.socket.readyState === WebSocket.OPEN) {
            socket.joinQueue();
          }
        }, 1000);
      }
    }, 1000);

    // Return cleanup function
    return () => {
      clearTimeout(queueTimeout);
    };
  };

  // Initialize from localStorage if available
  useEffect(() => {
    const savedColor = localStorage.getItem('chessPlayerColor');
    if (savedColor && (savedColor === 'white' || savedColor === 'black')) {
      console.log('Restoring player color from localStorage:', savedColor);
      setColor(savedColor);
    }
    
    // Also restore game ID if available
    const savedGameId = localStorage.getItem('currentGameId');
    if (savedGameId) {
      console.log('Restoring game ID from localStorage:', savedGameId);
      setGameId(savedGameId);
      setIsMatched(true); // Assume we're in a match if we have a game ID
      setHasAgreed(true); // Skip the agreement step on reconnection
    }
  }, []);
  
  // Save color to localStorage whenever it changes
  useEffect(() => {
    if (color === 'white' || color === 'black') {
      localStorage.setItem('chessPlayerColor', color);
      console.log('Saved player color to localStorage:', color);
    }
  }, [color]);

  useEffect(() => {
    // Check if user is authenticated
    const token = localStorage.getItem('userToken');
    if (!token) {
      navigate('/login');
      return;
    }

    // Initial WebSocket connection
    connectWebSocket();

    // Setup game state recovery on reconnection
    const handleReconnection = () => {
      // First restore game ID from localStorage if it's not already set
      const savedGameId = localStorage.getItem('currentGameId');
      const currentGameId = gameId || savedGameId;
      
      // Only attempt game state recovery if we have a game ID
      if (currentGameId) {
        console.log(`Attempting to recover game state after reconnection for game: ${currentGameId}`);
        
        // Make sure the gameId state is set
        if (!gameId && savedGameId) {
          setGameId(savedGameId);
          setIsMatched(true);
          setHasAgreed(true);
        }
        
        // Request current game state from server
        if (socketRef.current) {
          // Reset the chess instance to ensure we start with a clean state
          chess.reset();
          setFen(chess.fen());
          setMoveHistory([]);
          
          const success = socketRef.current.requestGameState(currentGameId);
          
          if (success) {
            setErrorMessage('Connection restored. Requesting current game state...');
          } else {
            // Try again after a short delay - socket might not be fully ready
            setTimeout(() => {
              if (socketRef.current) {
                const retrySuccess = socketRef.current.requestGameState(currentGameId);
                if (retrySuccess) {
                  setErrorMessage('Connection restored. Requesting current game state...');
                } else {
                  setErrorMessage('Unable to restore game state. Please refresh the page.');
                }
              }
            }, 1000);
          }
        } else {
          setErrorMessage('Connection error. Please refresh the page.');
        }
      }
    };

    // Add a listener for connection status changes
    if (socketRef.current) {
      const originalOnConnected = socketRef.current.onConnectedHandler;
      socketRef.current.onConnected((data) => {
        if (originalOnConnected) originalOnConnected(data);
        if (reconnectAttempts > 0) {
          handleReconnection();
        }
      });
    }

    // Cleanup on unmount
    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  const handleMove = async (move) => {
    // Only allow moves when it's user's turn and game is active
    if (!isMyTurn || gameStatus) {
      return false;
    }

    try {
      // Store the current FEN before move
      const prevFen = chess.fen();
      
      // Attempt the move in the chess instance
      const result = chess.move(move);

      if (!result) {
        return false; // Invalid move
      }

      // Update UI state - preserve board orientation by making atomic state updates
      const newFen = chess.fen();
      const newMoveHistory = [...moveHistory, result.san];
      
      setFen(newFen);
      setMoveHistory(newMoveHistory);
      setIsMyTurn(false); // Now opponent's turn

      // Sign the move with private key
      const privateKey = localStorage.getItem('userPrivateKey');
      if (!privateKey) {
        setErrorMessage('Private key not found. Please log in again.');
        // Revert the move if signing fails
        chess.load(prevFen);
        setFen(prevFen);
        setIsMyTurn(true);
        return false;
      }

      const wallet = new ethers.Wallet(privateKey);
      const moveData = JSON.stringify({ 
        from: move.from, 
        to: move.to, 
        fen: newFen,
        gameId: gameId,
      });
      const signature = await wallet.signMessage(moveData);

      // Send move to the server via WebSocket for real-time play
      if (socketRef.current) {
        console.log(`Sending move: ${move.from} to ${move.to}`);
        socketRef.current.sendMove(gameId, move, signature);
      }

      return true; // Move accepted
    } catch (error) {
      console.error('Error handling move:', error);
      setErrorMessage('Error making move. Please try again.');
      return false;
    }
  };

  const handleAgreeToRules = () => {
    setHasAgreed(true);
  };

  const handleResign = () => {
    if (!gameId || gameStatus) return;

    // Don't update local game state until server confirms
    // This prevents desynchronization between players
    if (socketRef.current) {
      console.log(`Player ${color} is resigning game ${gameId}`);
      socketRef.current.resign(gameId);
      
      // Only update local UI to show loading state
      setErrorMessage('Submitting resignation...');
      setTimeout(() => {
        if (!gameStatus) {
          // If server hasn't responded in 2 seconds, update locally
          console.log('Server did not confirm resignation, updating locally');
          setGameStatus({
            winner: color === 'white' ? 'black' : 'white',
            reason: 'resignation',
            perspective: color
          });
          setErrorMessage('');
        }
      }, 2000);
    }
  };

  const handleOfferDraw = () => {
    if (!gameId || gameStatus || drawOffered) return;

    if (socketRef.current) {
      socketRef.current.offerDraw(gameId);
    }
  };

  const handleDrawResponse = (accept) => {
    if (!gameId || !drawOffered) return;

    if (socketRef.current) {
      socketRef.current.respondToDrawOffer(gameId, accept);
    }

    if (accept) {
      // Update local game status
      setGameStatus({
        winner: null,
        reason: 'draw_agreement'
      });
    }

    setDrawOffered(false);
  };

  // Game status display message
  const getStatusMessage = () => {
    if (gameStatus) {
      // Handle game over scenarios
      if (gameStatus.winner === null) {
        return "Game ended in a draw.";
      } 
      
      const playerColor = color || 'white';
      const playerWon = gameStatus.winner === playerColor;
      
      if (playerWon) {
        if (gameStatus.reason === 'resignation') {
          return "You won! Your opponent resigned.";
        } else {
          return "You won by checkmate!";
        }
      } else {
        if (gameStatus.reason === 'resignation') {
          return "You resigned. Your opponent won.";
        } else {
          return "You lost by checkmate.";
        }
      }
    } else if (drawOffered) {
      return "Draw offer received. Do you accept?";
    } else if (isMyTurn) {
      return "Your turn.";
    } else {
      return "Opponent's turn.";
    }
  };

  return (
    <div className="min-vh-100 text-white d-flex flex-column p-4 position-relative">
      <div className="position-absolute top-0 start-0 end-0 bottom-0 bg-dark opacity-50"></div>
      <div className="container position-relative mt-5" style={{zIndex: "10", maxWidth: "900px"}}>
        <h1 className="fs-2 fw-bold mb-4 text-center" style={{color: '#d4af37'}}>Chess Game</h1>

        {!isMatched ? (
          <div className="glass-card p-4 text-center">
            <p className="text-light">Waiting for an opponent...</p>
          </div>
        ) : !hasAgreed ? (
          <div className="glass-card p-4 text-center">
            <p className="text-light mb-3">
              You have been matched with <strong>{opponent.username || `Player ${opponent.id.substring(0, 8)}`}</strong>
              {opponent.rating ? ` (Rating: ${opponent.rating})` : ''}.
              By playing, you agree to sign each move with your private key for blockchain verification.
            </p>
            <button onClick={handleAgreeToRules} className="btn btn-warning">
              I Agree
            </button>
          </div>
        ) : (
          <div className="row g-4">
            {errorMessage && (
              <div className="col-12">
                <div className="alert alert-danger">{errorMessage}</div>
              </div>
            )}

            <div className="col-md-7">
              <div className="glass-card p-3">
                {/* Opponent info banner */}
                <div className="mb-2 p-2 bg-dark bg-opacity-75 text-center rounded">
                  <div className="d-flex justify-content-between align-items-center">
                    <div>
                      <span className="badge bg-secondary me-2">{color === 'white' ? 'Black' : 'White'}</span>
                    </div>
                    <div>
                      <strong className="text-light">{opponent.username || `Player ${opponent.id.substring(0, 8)}`}</strong>
                      {opponent.rating && <span className="text-warning ms-2">Rating: {opponent.rating}</span>}
                    </div>
                    <div>
                      {opponent.wins !== undefined && opponent.losses !== undefined && (
                        <span className="text-info">
                          <small>W: {opponent.wins || 0} L: {opponent.losses || 0}</small>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                
                {/* Game status banner */}
                <div className="mb-3 p-2 bg-dark bg-opacity-50 text-center rounded">
                  <p className="mb-0 text-light">{getStatusMessage()}</p>

                  {/* Draw offer response buttons */}
                  {drawOffered && !gameStatus && (
                    <div className="mt-2">
                      <button 
                        onClick={() => handleDrawResponse(true)} 
                        className="btn btn-sm btn-success me-2">
                        Accept Draw
                      </button>
                      <button 
                        onClick={() => handleDrawResponse(false)} 
                        className="btn btn-sm btn-danger">
                        Decline Draw
                      </button>
                    </div>
                  )}
                </div>

                <div className="board-container" key={`board-container-${color}`}>
                  <Chessboard
                    position={fen}
                    boardOrientation={color === 'black' ? 'black' : 'white'}
                    onPieceDrop={(sourceSquare, targetSquare) => {
                      const move = { from: sourceSquare, to: targetSquare };
                      return handleMove(move);
                    }}
                    boardWidth={400}
                    areArrowsAllowed={true}
                    animationDuration={300}
                    clearPremovesOnRightClick={true}
                    id={`chess-board-${color}`} // Fixed ID to prevent re-renders causing rotation
                    customBoardStyle={{
                      borderRadius: '4px',
                      boxShadow: '0 2px 10px rgba(0, 0, 0, 0.5)'
                    }}
                  />
                  
                  {/* Orientation indicator to help players identify their position */}
                  <div className="orientation-indicator mt-1 text-center">
                    <span className="badge bg-dark">Playing as {color}</span>
                  </div>
                </div>

                {/* Game control buttons */}
                {!gameStatus && (
                  <div className="d-flex justify-content-between mt-3">
                    <button 
                      onClick={handleResign} 
                      className="btn btn-sm btn-danger">
                      Resign
                    </button>
                    <button 
                      onClick={handleOfferDraw} 
                      className="btn btn-sm btn-secondary" 
                      disabled={drawOffered}>
                      Offer Draw
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="col-md-5">
              <div className="glass-card p-3 h-100">
                <h2 className="fs-4 fw-semibold mb-3" style={{color: '#d4af37'}}>Game Info</h2>

                <div className="mb-3">
                  <p className="mb-1"><strong>Your color:</strong> {color.charAt(0).toUpperCase() + color.slice(1)}</p>
                  <p className="mb-1"><strong>Opponent:</strong> {opponent?.username || 'Unknown'}</p>
                </div>

                <h3 className="fs-5 fw-semibold mb-2" style={{color: '#d4af37'}}>Move History</h3>
                <div className="bg-dark bg-opacity-50 rounded p-2 mb-3" style={{maxHeight: '200px', overflowY: 'auto'}}>
                  {moveHistory.length > 0 ? (
                    <ol className="list-group list-group-flush bg-transparent">
                      {moveHistory.map((move, index) => (
                        <li key={index} className="list-group-item bg-transparent text-light border-secondary border-opacity-25">
                          {Math.floor(index/2) + 1}. {index % 2 === 0 ? '' : '...'} {move}
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="text-light text-center fst-italic mb-0">No moves yet</p>
                  )}
                </div>

                <div className="mt-3 p-2 bg-dark bg-opacity-50 rounded">
                  <h4 className="fs-6 fw-semibold" style={{color: '#d4af37'}}>Blockchain Verification</h4>
                  <p className="text-light small mb-1">
                    Each move is cryptographically signed and can be verified on the blockchain.
                  </p>
                  {gameId && (
                    <p className="text-light small mb-0">
                      Game ID: <code className="bg-dark p-1 rounded">{gameId}</code>
                    </p>
                  )}
                </div>

                <div className="mt-3 p-2 bg-dark bg-opacity-50 rounded">
                  <h4 className="fs-6 fw-semibold" style={{color: '#d4af37'}}>Connection Status</h4>
                  <p className="text-light small mb-0">
                    Status: <span className={`text-${connectionStatus === 'connected' ? 'success' : connectionStatus === 'connecting' ? 'warning' : 'danger'}`}>
                      {connectionStatus.charAt(0).toUpperCase() + connectionStatus.slice(1)}
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default Game;