// Simplified auth controller for development only
// This version works without requiring admin privileges
const jwt = require('jsonwebtoken');
const { ethers } = require('ethers');
const { supabase } = require('../utils/supabase');

/**
 * Register a new user - Dev friendly version
 */
async function register(req, res) {
  try {
    console.log('🚀 Received registration request:', JSON.stringify({
      ...req.body,
      password: '***REDACTED***' // Don't log passwords
    }, null, 2));
    
    const { username, email, password, publicKey } = req.body;
    
    // Validate input and log any missing fields
    if (!username || !email || !password || !publicKey) {
      console.log('❌ Missing registration fields');
      return res.status(400).json({ 
        success: false, 
        message: 'Please provide username, email, password and publicKey' 
      });
    }
    
    // Format public key
    let formattedPublicKey = publicKey;
    if (!formattedPublicKey.startsWith('0x')) {
      formattedPublicKey = '0x' + formattedPublicKey;
      console.log('Added 0x prefix to public key:', formattedPublicKey);
    }
    
    // Check if we have this email in users table
    const { data: existingUser } = await supabase
      .from('users')
      .select('email')
      .eq('email', email)
      .single();
      
    if (existingUser) {
      return res.status(400).json({ 
        success: false, 
        message: 'Email already in use' 
      });
    }

    // For development use only - we're not hitting the rate limit
    // This will still send a confirmation email which is required,
    // but we'll return a success anyway for development convenience
    
    console.log('Using standard signup (confirmation email will be sent)');
    const { data: authUser, error: authError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: `${process.env.FRONTEND_URL || 'http://localhost:3000'}/login`,
        data: {
          username,
          public_key: formattedPublicKey
        }
      }
    });
    
    if (authError) {
      console.error('❌ Error during signup:', authError);
      
      if (authError.code === 'over_email_send_rate_limit') {
        // Return a special message for rate limiting
        return res.status(429).json({
          success: false,
          message: 'Email rate limit reached. For development, use a unique email or wait an hour.'
        });
      }
      
      return res.status(500).json({
        success: false,
        message: `Registration error: ${authError.message}`
      });
    }

    // In a real app, we would wait for email confirmation before continuing.
    // For development, we'll generate a token immediately.
    console.log('✅ Auth user created, confirmation email sent');
    console.log('⚠️ Development mode: returning success even though email verification is needed');
    
    const token = jwt.sign(
      { id: authUser.user.id, email, username, publicKey: formattedPublicKey },
      process.env.JWT_SECRET || 'dev-secret',
      { expiresIn: '7d' }
    );
    
    // IMPORTANT: In real app, we'd create the user record after email confirmation.
    // For development, we can add the users table entry here, but it will likely fail
    // due to the foreign key constraint until email is confirmed.
    
    // Return success response
    return res.status(200).json({
      success: true,
      message: 'Registration initiated. Check your email to confirm your account.',
      developmentNote: 'For development: Use the token below even though email is not yet confirmed',
      token,
      user: {
        id: authUser.user.id,
        username,
        email,
        publicKey: formattedPublicKey
      }
    });
  } catch (error) {
    console.error('Registration error:', error);
    return res.status(500).json({ 
      success: false, 
      message: 'Server error during registration' 
    });
  }
}

/**
 * Login a user
 */
async function login(req, res) {
  try {
    const { email, password } = req.body;
    
    // Validate input
    if (!email || !password) {
      return res.status(400).json({ 
        success: false, 
        message: 'Please provide email and password' 
      });
    }
    
    // Sign in with Supabase Auth
    const { data: authData, error: authError } = await supabase.auth.signInWithPassword({
      email,
      password
    });
    
    if (authError) {
      console.log('Login error:', authError);
      
      if (authError.message.includes('Email not confirmed')) {
        // For development - return information about email confirmation
        return res.status(401).json({ 
          success: false, 
          message: 'Email not confirmed. Check your email for the confirmation link.',
          devNote: 'For development, you can use the Supabase dashboard to manually confirm the email.'
        });
      }
      
      return res.status(401).json({ 
        success: false, 
        message: 'Invalid credentials' 
      });
    }
    
    // Get user data from auth metadata first (in case user table entry doesn't exist yet)
    console.log('User authenticated, getting user data');
    
    let userData = null;
    
    // Try to get from users table
    const { data: dbUser, error: dbError } = await supabase
      .from('users')
      .select('*')
      .eq('id', authData.user.id)
      .single();
    
    if (dbError || !dbUser) {
      console.log('User not found in database, using auth metadata');
      
      // User might not be in our table yet (if email just confirmed)
      // Create an object from the auth metadata
      userData = {
        id: authData.user.id,
        username: authData.user.user_metadata.username || email.split('@')[0],
        email: authData.user.email,
        public_key: authData.user.user_metadata.public_key || '',
        rating: 1200
      };
      
      // Try to insert the user now (might work if email is confirmed)
      console.log('Attempting to create user profile on first login');
      try {
        await supabase
          .from('users')
          .insert([{
            id: userData.id,
            username: userData.username,
            email: userData.email,
            public_key: userData.public_key,
            rating: 1200
          }]);
        console.log('User profile created on first login');
      } catch (insertError) {
        console.error('Could not create user profile:', insertError);
        // Continue anyway, using the auth metadata
      }
    } else {
      userData = dbUser;
    }
    
    // Generate JWT token
    const token = jwt.sign(
      { 
        id: userData.id, 
        email: userData.email, 
        username: userData.username,
        publicKey: userData.public_key || ''
      },
      process.env.JWT_SECRET || 'dev-secret',
      { expiresIn: '7d' }
    );
    
    // Return success
    return res.status(200).json({
      success: true,
      token,
      user: {
        id: userData.id,
        username: userData.username,
        email: userData.email,
        publicKey: userData.public_key || '',
        rating: userData.rating || 1200
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

// Keep other functions as placeholders
function verifyEmail(req, res) {
  res.redirect(`${process.env.FRONTEND_URL || 'http://localhost:3000'}/login?verified=true`);
}

function forgotPassword(req, res) {
  res.status(200).json({ 
    success: true, 
    message: 'Password reset link sent if email exists' 
  });
}

function resetPassword(req, res) {
  res.status(200).json({ 
    success: true, 
    message: 'Password updated successfully' 
  });
}

module.exports = {
  register,
  login,
  verifyEmail,
  forgotPassword,
  resetPassword
};
