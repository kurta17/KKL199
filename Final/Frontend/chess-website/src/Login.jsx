import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { authAPI } from './services/api';

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  // Check if user is already logged in
  useEffect(() => {
    const token = localStorage.getItem('userToken');
    if (token) {
      navigate('/game');
    }
  }, [navigate]);

  // Handle normal login
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    // Validate form
    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }
    
    setIsLoading(true);
    
    try {
      // Use the authAPI service
      const response = await authAPI.login({ email, password });
      
      if (response.success) {
        // Store user data in localStorage
        localStorage.setItem('userToken', response.token);
        localStorage.setItem('userId', response.user.id);
        localStorage.setItem('userEmail', response.user.email);
        localStorage.setItem('userName', response.user.username);
        localStorage.setItem('userPublicKey', response.user.publicKey);
        
        // If private key was stored during registration, it should be in localStorage already
        // We don't retrieve it from the server for security reasons
        const privateKey = localStorage.getItem('userPrivateKey');
        if (!privateKey) {
          console.warn('No private key found in localStorage. Signature verification will not work.');
        }
        
        // Redirect to game page
        navigate('/game');
      } else {
        setError(response.message || 'Failed to login.');
      }
    } catch (err) {
      console.error('Login error:', err);
      setError('Failed to login. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };
  
  // Development mode: Force login without email confirmation
  const handleDevForceLogin = async (e) => {
    e.preventDefault();
    setError('');
    
    // Validate form
    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }
    
    setIsLoading(true);
    
    try {
      // Use the development bypass function
      const response = await authAPI.devForceLogin({ email, password });
      
      if (response.success) {
        // Store user data in localStorage
        localStorage.setItem('userToken', response.token);
        localStorage.setItem('userId', response.user.id);
        localStorage.setItem('userEmail', response.user.email);
        localStorage.setItem('userName', response.user.username);
        localStorage.setItem('userPublicKey', response.user.publicKey);
        localStorage.setItem('devMode', 'true'); // Mark as dev mode auth
        
        // Redirect to game page
        navigate('/game');
      } else {
        setError(response.message || 'Failed to login with development bypass.');
      }
    } catch (err) {
      console.error('Dev login error:', err);
      setError('Failed to login with development bypass. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-vh-100 text-white d-flex flex-column justify-content-center p-4 position-relative">
      <div className="position-absolute top-0 start-0 end-0 bottom-0 bg-dark opacity-50"></div>
      <div className="mx-auto glass-card p-4 position-relative" style={{maxWidth: "400px"}}>
        <div className="text-center mb-4">
          <Link to="/">
            <h1 className="fs-2 fw-bold mb-2" style={{color: '#d4af37'}}>
              ChainChess
            </h1>
          </Link>
          <p className="text-light">Welcome back, strategist.</p>
        </div>

        {error && (
          <div className="alert alert-danger text-center mb-3">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="mb-3">
            <label htmlFor="email" className="form-label text-light">
              Email Address
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="form-control bg-dark text-light border-secondary"
              placeholder="you@example.com"
              disabled={isLoading}
              required
            />
          </div>
          
          <div className="mb-4">
            <label htmlFor="password" className="form-label text-light">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="form-control bg-dark text-light border-secondary"
              placeholder="••••••••"
              disabled={isLoading}
              required
            />
          </div>
          
          <button
            type="submit"
            disabled={isLoading}
            className="btn btn-warning w-100 mb-3"
          >
            {isLoading ? (
              <>
                <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                Loading...
              </>
            ) : (
              'Sign In'
            )}
          </button>
          
          {/* Development-only button for bypassing email verification */}
          {import.meta.env.DEV && (
            <button
              type="button"
              onClick={handleDevForceLogin}
              disabled={isLoading}
              className="btn btn-danger w-100 mb-3"
            >
              {isLoading ? (
                <>
                  <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                  Loading...
                </>
              ) : (
                'DEV MODE: Skip Email Verification'
              )}
            </button>
          )}
        </form>
        
        <p className="mt-4 text-center text-light">
          Not a member?{' '}
          <Link to="/register" className="text-warning text-decoration-none">
            Register here
          </Link>
        </p>
      </div>
    </div>
  );
}

export default Login;