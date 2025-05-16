/**
 * Simple Bypass Auth Controller
 * 
 * This is a simplified controller that bypasses Supabase authentication
 * It uses minimal dependencies and direct database insertion
 */

const { v4: uuidv4 } = require('uuid');
const jwt = require('jsonwebtoken');
const { supabase } = require('../utils/supabase');

/**
 * Register a user bypassing all auth checks
 */
async function register(req, res) {
  try {
    console.log('🛠️ Simple Bypass Auth: Registration request received');
    
    const { username, email, password, publicKey } = req.body;
    
    // Basic validation
    if (!username || !email || !password || !publicKey) {
      return res.status(400).json({
        success: false,
        message: 'Missing required fields'
      });
    }
    
    // Generate a UUID for the user
    const userId = uuidv4();
    console.log('Generated user ID:', userId);
    
    // Format public key if necessary
    let formattedPublicKey = publicKey;
    if (!formattedPublicKey.startsWith('0x')) {
      formattedPublicKey = '0x' + formattedPublicKey;
    }
    
    // Create the user object
    const userObject = {
      id: userId,
      username,
      email,
      public_key: formattedPublicKey,
      rating: 1200,
      created_at: new Date(),
      wins: 0,
      losses: 0,
      draws: 0
    };
    
    console.log('Inserting user directly:', userObject);
    
    // Insert into the users table directly
    const { error: insertError } = await supabase
      .from('users')
      .insert([userObject]);
      
    if (insertError) {
      console.error('Error inserting user:', insertError);
      return res.status(500).json({
        success: false,
        message: 'Database error: ' + insertError.message
      });
    }
    
    // Generate a JWT token
    const token = jwt.sign(
      { 
        id: userId, 
        email, 
        username,
        publicKey: formattedPublicKey
      },
      process.env.JWT_SECRET || 'dev-secret-key',
      { expiresIn: '7d' }
    );
    
    // Return success with token
    console.log('User created successfully:', userId);
    return res.status(201).json({
      success: true,
      message: 'User registered successfully (bypass mode)',
      token,
      user: {
        id: userId,
        username,
        email,
        publicKey: formattedPublicKey
      }
    });
    
  } catch (error) {
    console.error('Simple bypass registration error:', error);
    return res.status(500).json({
      success: false,
      message: 'Server error'
    });
  }
}

/**
 * Login a user directly
 */
async function login(req, res) {
  try {
    const { email, password } = req.body;
    
    // Find user by email
    const { data: user, error } = await supabase
      .from('users')
      .select('*')
      .eq('email', email)
      .single();
    
    if (error || !user) {
      return res.status(401).json({
        success: false,
        message: 'Invalid credentials'
      });
    }
    
    // In bypass mode, we don't check password
    console.log('Bypass login successful for:', user.email);
    
    // Generate a JWT token
    const token = jwt.sign(
      { 
        id: user.id, 
        email: user.email, 
        username: user.username,
        publicKey: user.public_key
      },
      process.env.JWT_SECRET || 'dev-secret-key',
      { expiresIn: '7d' }
    );
    
    // Return success with token
    return res.status(200).json({
      success: true,
      message: 'Login successful (bypass mode)',
      token,
      user: {
        id: user.id,
        username: user.username,
        email: user.email,
        publicKey: user.public_key,
        rating: user.rating
      }
    });
    
  } catch (error) {
    console.error('Simple bypass login error:', error);
    return res.status(500).json({
      success: false,
      message: 'Server error'
    });
  }
}

module.exports = {
  register,
  login
};
