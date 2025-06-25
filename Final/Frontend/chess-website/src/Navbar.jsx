import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';

function Navbar() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    setIsAuthenticated(!!localStorage.getItem('userToken'));
  }, [location]);

  const handleLogout = () => {
    localStorage.removeItem('userToken');
    localStorage.removeItem('userPrivateKey');
    setIsAuthenticated(false);
    navigate('/login');
  };

  return (
    <nav className="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
      <div className="container-fluid">
        <Link className="navbar-brand text-warning fw-bold" to="/">ChainChess</Link>
        
        <button className="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
          <span className="navbar-toggler-icon"></span>
        </button>
        
        <div className="collapse navbar-collapse justify-content-end" id="navbarNav">
          <ul className="navbar-nav">
            <li className="nav-item">
              <Link className={`nav-link ${location.pathname === '/' ? 'active fw-bold' : ''}`} to="/">Home</Link>
            </li>
            <li className="nav-item">
              <Link className={`nav-link ${location.pathname === '/game' ? 'active fw-bold' : ''}`} to="/game">Play Game</Link>
            </li>
            {!isAuthenticated ? (
              <>
                <li className="nav-item">
                  <Link className={`nav-link ${location.pathname === '/login' ? 'active fw-bold' : ''}`} to="/login">Login</Link>
                </li>
                <li className="nav-item">
                  <Link className="nav-link btn btn-warning btn-sm text-dark ms-2 px-3" to="/register">Register</Link>
                </li>
              </>
            ) : (
              <li className="nav-item">
                <button onClick={handleLogout} className="nav-link btn btn-danger btn-sm text-white ms-2 px-3">
                  Logout
                </button>
              </li>
            )}
          </ul>
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
