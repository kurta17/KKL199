import React from 'react';
import { Link } from 'react-router-dom';

function Welcome() {
  return (
    <div className="min-vh-100 text-white d-flex flex-column align-items-center justify-content-center p-4 position-relative">
      <div className="position-absolute top-0 start-0 end-0 bottom-0 bg-dark opacity-50"></div>
      <header className="text-center mb-5 position-relative">
        <h1 className="display-4 fw-bold mb-3" style={{color: '#d4af37'}}>
          ChainChess
        </h1>
        <p className="lead text-light">A Decentralized Chess Revolution</p>
      </header>

      <div className="d-flex flex-column gap-4 mx-auto mb-5 position-relative" style={{maxWidth: "800px"}}>
        <div className="glass-card p-4 text-center" style={{transition: "transform 0.3s"}} 
             onMouseEnter={(e) => e.currentTarget.style.transform = "scale(1.03)"} 
             onMouseLeave={(e) => e.currentTarget.style.transform = "scale(1)"}>
          <h2 className="fs-3 fw-semibold mb-3" style={{color: '#d4af37'}}>Play on the Blockchain</h2>
          <p className="text-light mb-4">
            Challenge opponents, record your moves immutably, and own your game history with blockchain technology.
          </p>
          <Link
            to="/game"
            className="btn btn-outline-warning"
          >
            Enter the Arena
          </Link>
        </div>
        
        <div className="glass-card p-4 text-center" style={{transition: "transform 0.3s"}} 
             onMouseEnter={(e) => e.currentTarget.style.transform = "scale(1.03)"} 
             onMouseLeave={(e) => e.currentTarget.style.transform = "scale(1)"}>
          <h2 className="fs-3 fw-semibold mb-3" style={{color: '#d4af37'}}>Secure & Transparent</h2>
          <p className="text-light mb-4">
            Powered by Merkle trees and gossip protocols for secure, decentralized gameplay.
          </p>
          <div className="d-flex flex-column flex-md-row gap-3 justify-content-center">
            <Link
              to="/login"
              className="btn btn-outline-light flex-fill"
            >
              Login
            </Link>
            <Link
              to="/register"
              className="btn btn-warning flex-fill"
            >
              Register
            </Link>
          </div>
        </div>
      </div>

      <footer className="text-center text-light mt-auto pb-3 position-relative">
        <p>© {new Date().getFullYear()} ChainChess. All rights reserved.</p>
      </footer>
    </div>
  );
}

export default Welcome;