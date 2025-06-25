import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import nacl from 'tweetnacl';
import base64js from 'base64-js';
import { authAPI } from './services/api';

function Register() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [privateKey, setPrivateKey] = useState('');
  const [publicKey, setPublicKey] = useState('');
  const [showKeysModal, setShowKeysModal] = useState(false);
  const navigate = useNavigate();

  // Check if user is already logged in
  useEffect(() => {
    const token = localStorage.getItem('userToken');
    if (token) {
      navigate('/game');
    }
  }, [navigate]);

  // Generate Ed25519 keypair
  useEffect(() => {
    try {
      // Generate a new Ed25519 keypair
      const keyPair = nacl.sign.keyPair();
      
      // Convert the keys to base64 for storage
      const privateKeyBase64 = base64js.fromByteArray(keyPair.secretKey);
      const publicKeyBase64 = base64js.fromByteArray(keyPair.publicKey);
      
      console.log('Generated Ed25519 private key (base64):', privateKeyBase64);
      console.log('Generated Ed25519 public key (base64):', publicKeyBase64);
      
      setPrivateKey(privateKeyBase64);
      setPublicKey(publicKeyBase64);
    } catch (error) {
      console.error('Error generating Ed25519 keys:', error);
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    // Form validation
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    
    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }
    
    if (!username || username.length < 3) {
      setError('Username must be at least 3 characters long.');
      return;
    }
    
    // More comprehensive email validation
    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!email || !emailRegex.test(email)) {
      setError('Please enter a valid email address. Use a real email provider (e.g., gmail.com, outlook.com).');
      return;
    }
    
    setIsLoading(true);
    
    try {
      // Register user via API service
      console.log('Sending registration with public key:', publicKey);
      const registrationData = {
        username,
        email,
        password,
        publicKey
      };        console.log('Registration payload:', {
          ...registrationData,
          publicKey: registrationData.publicKey.substring(0, 10) + '...' // Only show part of the key for security
        });
      
      // Store private key in localStorage BEFORE registration attempt
      // This way we have the key even if the user refreshes later
      localStorage.setItem('userPrivateKey', privateKey);
      
      let response = await authAPI.register(registrationData);
      console.log('Registration response:', response);
      
      // If regular registration fails and we're in development mode,
      // ALWAYS try the bypass registration method immediately
      if (!response.success && import.meta.env.DEV) {
        console.log('🔄 Regular registration failed, attempting bypass in dev mode...');
        console.log('📋 Error message:', response.message);
        
        // In development, immediately use the bypass system without checking specific errors
        // This ensures we can continue development even with any auth issues
        console.warn('⚠️ Using bypass registration for development - NOT FOR PRODUCTION ⚠️');
        
        try {
          // Add a small delay to ensure any database operations complete
          await new Promise(resolve => setTimeout(resolve, 500));
          
          console.log('🔄 Calling bypass registration with:', {
            username: registrationData.username,
            email: registrationData.email,
            publicKey: registrationData.publicKey.substring(0, 10) + '...'
          });
          
          // Call the bypass registration
          response = await authAPI.bypassRegister(registrationData);
          console.log('✅ Bypass registration response:', response);
          
          // If bypass still failed, show a more helpful error message
          if (!response.success) {
            console.error('❌ Bypass registration also failed!');
            setError('Registration failed: ' + (response.message || 'Unknown error'));
          } else {
            console.log('✅ Bypass registration successful!');
          }
        } catch (bypassError) {
          console.error('❌ Error during bypass registration:', bypassError);
          setError('Registration system error. Please try again or contact support.');
        }
      }
      
      if (response.success) {
        console.log('Registration successful!', response);
        
        // Store authentication data
        localStorage.setItem('userToken', response.token);
        localStorage.setItem('userPrivateKey', privateKey);
        localStorage.setItem('userId', response.user.id);
        localStorage.setItem('userEmail', response.user.email);
        localStorage.setItem('userName', response.user.username);
        
        // Make sure we're storing the correct public key - use the one from the wallet generation
        // as the server may have reformatted it
        localStorage.setItem('userPublicKey', publicKey);
        
        console.log('Saved user data to localStorage with publicKey:', publicKey);
        
        // Show keys modal
        setShowKeysModal(true);
      } else {
        setError(response.message || 'Failed to register.');
      }
    } catch (err) {
      console.error('Registration error:', err);
      setError('Failed to register. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleContinue = () => {
    setShowKeysModal(false);
    navigate('/game');
  };

  const handleCopyKey = () => {
    navigator.clipboard.writeText(privateKey);
    alert("Private key copied to clipboard!");
  };
  
  const handleDownloadKey = () => {
    const element = document.createElement("a");
    const file = new Blob([
      `ChainChess Cryptographic Keys\n\nUsername: ${username}\nPublic Key: ${publicKey}\nPrivate Key: ${privateKey}\n\nIMPORTANT: Keep your private key secure! Anyone with your private key can sign moves on your behalf.`
    ], {type: 'text/plain'});
    element.href = URL.createObjectURL(file);
    element.download = "chainchess_keys.txt";
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  return (
    <div className="min-vh-100 text-white d-flex flex-column justify-content-center p-4 position-relative">
      <div className="position-absolute top-0 start-0 end-0 bottom-0 bg-dark opacity-50"></div>
      <div className="mx-auto glass-card p-4 position-relative" style={{maxWidth: "400px"}}>
        {!showKeysModal ? (
          <>
            <div className="text-center mb-4">
              <Link to="/">
                <h1 className="fs-2 fw-bold mb-2" style={{color: '#d4af37'}}>
                  Join ChainChess
                </h1>
              </Link>
              <p className="text-light">Create your decentralized chess identity.</p>
            </div>

            {error && (
              <div className="alert alert-danger text-center mb-3">
                {error}
              </div>
            )}
          </>
        ) : (
          <div className="text-center">
            <h2 className="fs-3 fw-bold mb-3" style={{color: '#d4af37'}}>Important: Secure Your Keys</h2>
            <div className="alert alert-warning">
              <p className="mb-2"><strong>Your account has been created successfully!</strong></p>
              <p className="mb-0">Your private key has been generated. This key is used to sign your moves and verify your identity on the blockchain.</p>
            </div>
            
            <div className="bg-dark p-3 rounded mb-3">
              <p className="text-light mb-2"><strong>Private Key:</strong></p>
              <p className="text-light bg-black p-2 rounded small" style={{wordBreak: "break-all"}}>
                {privateKey}
              </p>
              <div className="d-flex justify-content-center gap-2 mt-3">
                <button onClick={handleCopyKey} className="btn btn-sm btn-secondary">
                  Copy Key
                </button>
                <button onClick={handleDownloadKey} className="btn btn-sm btn-info">
                  Download Key File
                </button>
              </div>
            </div>
            
            <div className="alert alert-danger">
              <strong>IMPORTANT:</strong> Store this key securely! If you lose it, you won't be able to sign your moves or recover your account.
            </div>
            
            <button className="btn btn-success w-100 mt-3" onClick={handleContinue}>
              I've Secured My Key - Continue to Game
            </button>
          </div>
        )}

        {!showKeysModal && (
          <>
            <form onSubmit={handleSubmit}>
              <div className="mb-3">
                <label htmlFor="username" className="form-label text-light">
                  Username
                </label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="form-control bg-dark text-light border-secondary"
                  placeholder="Your unique handle"
                  disabled={isLoading}
                  required
                />
              </div>
              
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
              
              <div className="mb-3">
                <label htmlFor="password" className="form-label text-light">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="form-control bg-dark text-light border-secondary"
                  placeholder="Min. 8 characters"
                  disabled={isLoading}
                  required
                />
              </div>
              
              <div className="mb-3">
                <label htmlFor="confirmPassword" className="form-label text-light">
                  Confirm Password
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="form-control bg-dark text-light border-secondary"
                  placeholder="Re-enter your password"
                  disabled={isLoading}
                  required
                />
              </div>
              
              <div className="alert alert-info mb-3">
                <h5 className="fs-6 fw-bold">Blockchain-Secured Identity</h5>
                <p className="small mb-0">
                  When you register, a cryptographic keypair will be generated for you. Your moves will be signed using this key, ensuring fair play and providing a cryptographic proof of each action.
                </p>
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
                  'Create Account'
                )}
              </button>
            </form>
            
            <p className="mt-4 text-center text-light">
              Already have an account?{' '}
              <Link to="/login" className="text-warning text-decoration-none">
                Sign in here
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default Register;