import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from './services/api';

function BlockchainExplorer() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [gameId, setGameId] = useState(searchParams.get('gameId') || '');
  const [gameHistory, setGameHistory] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [verification, setVerification] = useState({ status: 'unknown', details: [] });

  useEffect(() => {
    if (searchParams.get('gameId')) {
      fetchGameHistory(searchParams.get('gameId'));
    }
  }, [searchParams]);

  const fetchGameHistory = async (id) => {
    if (!id) return;
    
    setLoading(true);
    setError(null);
    setVerification({ status: 'unknown', details: [] });
    
    try {
      const response = await api.getBlockchainGameHistory(id);
      setGameHistory(response.data);
      verifyGameIntegrity(response.data.moves);
    } catch (err) {
      console.error('Error fetching game history:', err);
      setError('Failed to fetch game history from the blockchain. The game may not exist or the blockchain node is offline.');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    if (gameId) {
      navigate(`/explorer?gameId=${encodeURIComponent(gameId)}`);
      fetchGameHistory(gameId);
    }
  };

  const verifyGameIntegrity = (moves) => {
    if (!moves || moves.length === 0) {
      setVerification({
        status: 'unknown',
        details: ['No moves to verify']
      });
      return;
    }

    const details = [];
    let allSignaturesValid = true;
    let movesInSequence = true;
    let lastMoveNumber = -1;

    for (const move of moves) {
      if (move.move_number !== lastMoveNumber + 1) {
        movesInSequence = false;
        details.push(`Move sequence broken at move ${move.move_number}`);
      }
      lastMoveNumber = move.move_number;

      if (move.signature) {
        details.push(`Move ${move.move_number}: Signature present`);
      } else {
        allSignaturesValid = false;
        details.push(`Move ${move.move_number}: No signature`);
      }
    }

    if (allSignaturesValid && movesInSequence) {
      setVerification({
        status: 'verified',
        details
      });
    } else if (!allSignaturesValid) {
      setVerification({
        status: 'invalid',
        details
      });
    } else {
      setVerification({
        status: 'partial',
        details
      });
    }
  };

  return (
    <div className="container py-5">
      <div className="row justify-content-center">
        <div className="col-lg-10">
          <h1 className="text-warning fw-bold display-6 mb-4">
            ChessChain Explorer
          </h1>
          
          <div className="card bg-dark shadow mb-4">
            <div className="card-body">
              <h2 className="card-title text-white mb-4">Verify Game History</h2>
              <form onSubmit={handleSearch} className="d-flex gap-2">
                <input
                  type="text"
                  value={gameId}
                  onChange={(e) => setGameId(e.target.value)}
                  placeholder="Enter a game ID"
                  className="form-control bg-dark text-light border-secondary flex-grow-1"
                  required
                />
                <button
                  type="submit"
                  className="btn btn-warning fw-bold"
                  disabled={loading}
                >
                  {loading ? 'Searching...' : 'Search'}
                </button>
              </form>
            </div>
          </div>

          {error && (
            <div className="alert alert-danger" role="alert">
              {error}
            </div>
          )}

          {gameHistory && (
            <div className="card bg-dark shadow mb-4">
              <div className="card-body">
                <div className="d-flex justify-content-between align-items-center mb-4">
                  <h2 className="card-title text-white m-0">
                    Game {gameHistory.game_id}
                  </h2>
                  
                  <div className="d-flex align-items-center">
                    <span className="me-2 text-white">Verification:</span>
                    {verification.status === 'verified' && (
                      <span className="badge bg-success">
                        Verified
                      </span>
                    )}
                    {verification.status === 'invalid' && (
                      <span className="badge bg-danger">
                        Invalid
                      </span>
                    )}
                    {verification.status === 'partial' && (
                      <span className="badge bg-warning text-dark">
                        Partial
                      </span>
                    )}
                    {verification.status === 'unknown' && (
                      <span className="badge bg-secondary">
                        Unknown
                      </span>
                    )}
                  </div>
                </div>

                <div className="table-responsive">
                  <table className="table table-dark table-striped">
                    <thead>
                      <tr>
                        <th scope="col">#</th>
                        <th scope="col">Move</th>
                        <th scope="col">Piece</th>
                        <th scope="col">Player</th>
                        <th scope="col">Signature</th>
                      </tr>
                    </thead>
                    <tbody>
                      {gameHistory.moves.map((move, index) => (
                        <tr key={index}>
                          <td>{move.move_number}</td>
                          <td>{move.from_square} → {move.to_square}</td>
                          <td>
                            {move.piece}
                            {move.promotion ? ` → ${move.promotion}` : ''}
                          </td>
                          <td>
                            <span className="text-truncate d-inline-block" style={{maxWidth: "120px"}}>
                              {`${move.player_public_key.substring(0, 6)}...${move.player_public_key.substring(move.player_public_key.length - 4)}`}
                            </span>
                          </td>
                          <td>
                            {move.signature ? (
                              <span className="text-success">
                                {`${move.signature.substring(0, 6)}...${move.signature.substring(move.signature.length - 4)}`}
                              </span>
                            ) : (
                              <span className="text-danger">No signature</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="mt-4">
                  <h3 className="h5 text-white mb-3">Verification Details</h3>
                  <div className="bg-secondary bg-opacity-25 p-3 rounded">
                    <ul className="list-unstyled">
                      {verification.details.map((detail, i) => (
                        <li key={i} className="text-light small mb-1">• {detail}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="card bg-dark shadow">
            <div className="card-body">
              <h2 className="card-title text-white mb-4">About the ChessChain</h2>
              <p className="text-light mb-3">
                ChessChain is a blockchain specifically designed for recording chess games with cryptographic verification. 
                Each move is signed by the player's private key and recorded immutably on the blockchain.
              </p>
              <p className="text-light mb-4">
                The blockchain uses a Merkle tree data structure for transaction validation and employs 
                a gossip protocol for peer-to-peer communication, ensuring decentralization and security.
              </p>
              <div className="d-flex gap-3">
                <a 
                  href="#" 
                  onClick={(e) => {e.preventDefault(); alert("Documentation coming soon!");}} 
                  className="text-warning text-decoration-none"
                >
                  Technical Documentation
                </a>
                <a 
                  href="#" 
                  onClick={(e) => {e.preventDefault(); alert("GitHub repository link coming soon!");}} 
                  className="text-warning text-decoration-none"
                >
                  GitHub Repository
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default BlockchainExplorer;
