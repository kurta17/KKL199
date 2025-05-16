// ULTRA-SIMPLE DEMO MODE controller for registration
const jwt = require('jsonwebtoken');
const { ethers } = require('ethers');
const { v4: uuidv4 } = require('uuid');
const { supabase } = require('../utils/supabase');

/**
 * Register a user in DEMO mode
 * This completely bypasses email verification and foreign key constraints
 */
async function register(req, res) {
  try {
    console.log('🎮 DEMO MODE: Processing registration request:', JSON.stringify({
      ...req.body,
      password: '***REDACTED***'
    }, null, 2));
    
    const { username, email, password } = req.body;
    
    // Basic validation
    if (!username || !email || !password) {
      return res.status(400).json({ 
        success: false, 
        message: 'Please provide username, email, and password' 
      });
    }
    
    // Generate wallet for blockchain operations
    let publicKey;
    try {
      const wallet = ethers.Wallet.createRandom();
      publicKey = wallet.address;
      console.log('Generated wallet with address:', publicKey);
    } catch (error) {
      console.error('Error generating wallet:', error);
      publicKey = '0x' + '0'.repeat(40); // Fallback
    }
    
    // Generate a UUID for the user
    const userId = uuidv4();
    
    console.log(`📝 DEMO: Creating user with generated ID: ${userId}`);
    console.log(`📝 DEMO: Public key: ${publicKey}`);
    
    // Insert the user directly (bypass auth)
    const { data: newUser, error: insertError } = await supabase
      .from('users')
      .insert([{
        id: userId,
        username,
        email,
        public_key: publicKey,
        rating: 1200,
        created_at: new Date()
      }])
      .select();
      
    if (insertError) {
      console.error('❌ Error inserting user:', insertError);
      
      if (insertError.code === '23505') {
        return res.status(400).json({
          success: false,
          message: 'Email or username already exists'
        });
      }
      
      return res.status(500).json({
        success: false,
        message: 'Database error creating user',
        details: insertError.message
      });
    }
    
    console.log('✅ User created successfully!', newUser);
    
    // Create auth entry (try, but not critical in demo mode)
    try {
      const { error: authError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            username,
            public_key: publicKey
          }
        }
      });
      
      if (authError) {
        console.warn('⚠️ Auth creation failed, but continuing in demo mode:', authError);
      }
    } catch (authError) {
      console.warn('⚠️ Auth error ignored in demo mode:', authError);
    }
    
    // Generate token regardless of auth success
    const token = jwt.sign(
      { id: userId, email, username, publicKey },
      process.env.JWT_SECRET || 'demo-secret-key',
      { expiresIn: '30d' }
    );
    
    // DEMO MODE: Always store the private key (for demo only)
    // In production this should never leave the client
    
    // Return success with token
    return res.status(201).json({
      success: true,
      message: 'DEMO MODE: Registration successful!',
      token,
      user: {
        id: userId,
        username,
        email,
        publicKey
      }
    });
    
  } catch (error) {
    console.error('❌ Registration error:', error);
    return res.status(500).json({
      success: false,
      message: 'Server error during registration'
    });
  }
}

/**
 * Login a user in DEMO mode
 */
async function login(req, res) {
  try {
    const { email, password } = req.body;
    
    if (!email || !password) {
      return res.status(400).json({ 
        success: false, 
        message: 'Please provide email and password' 
      });
    }
    
    // Try normal login first
    const { data: authData, error: authError } = await supabase.auth.signInWithPassword({
      email,
      password
    });
    
    // If normal login fails in demo mode, look for the user in the users table
    if (authError) {
      console.log('Standard login failed, trying demo mode login');
      
      // Find user by email
      const { data: userData, error: userError } = await supabase
        .from('users')
        .select('*')
        .eq('email', email)
        .single();
        
      if (userError || !userData) {
        return res.status(401).json({
          success: false,
          message: 'Invalid credentials'
        });
      }
      
      // In demo mode, we don't verify the password beyond this point
      // Generate token
      const token = jwt.sign(
        { 
          id: userData.id, 
          email: userData.email, 
          username: userData.username,
          publicKey: userData.public_key
        },
        process.env.JWT_SECRET || 'demo-secret-key',
        { expiresIn: '7d' }
      );
      
      return res.status(200).json({
        success: true,
        message: 'DEMO MODE: Login successful!',
        token,
        user: {
          id: userData.id,
          username: userData.username,
          email: userData.email,
          publicKey: userData.public_key,
          rating: userData.rating
        }
      });
    }
    
    // If standard login succeeded, proceed normally
    const { data: userData, error: userError } = await supabase
      .from('users')
      .select('*')
      .eq('id', authData.user.id)
      .single();
      
    if (userError) {
      console.log('User not found in users table, creating entry');
      
      // In demo mode, create the user record if missing
      const demoUser = {
        id: authData.user.id,
        username: email.split('@')[0],
        email: email,
        public_key: '0x' + '1'.repeat(40),
        rating: 1200,
        created_at: new Date()
      };
      
      await supabase
        .from('users')
        .insert([demoUser]);
        
      userData = demoUser;
    }
    
    // Generate JWT token
    const token = jwt.sign(
      { 
        id: userData.id, 
        email: userData.email, 
        username: userData.username,
        publicKey: userData.public_key
      },
      process.env.JWT_SECRET || 'demo-secret-key',
      { expiresIn: '7d' }
    );
    
    return res.status(200).json({
      success: true,
      token,
      user: {
        id: userData.id,
        username: userData.username,
        email: userData.email,
        publicKey: userData.public_key,
        rating: userData.rating
      }
    });
    
  } catch (error) {
    console.error('Login error:', error);
    return res.status(500).json({
      success: false,
      message: 'Server error during login'
    });
  }
}

// Simplified stubs for other auth functions
async function verifyEmail(req, res) {
  res.redirect(`${process.env.FRONTEND_URL || 'http://localhost:3000'}/login?verified=true`);
}

async function forgotPassword(req, res) {
  res.status(200).json({ 
    success: true, 
    message: 'DEMO MODE: Password reset instructions would be sent here' 
  });
}

async function resetPassword(req, res) {
  res.status(200).json({ 
    success: true, 
    message: 'DEMO MODE: Password would be reset here' 
  });
}

module.exports = {
  register,
  login,
  verifyEmail,
  forgotPassword,
  resetPassword
};
