/**
 * Bypass Auth Controller
 * 
 * This controller provides methods for bypassing Supabase auth restrictions
 * in development environments. It allows:
 * 
 * 1. Direct user creation without email verification
 * 2. Direct user insertion into public.users table without foreign key constraints
 * 3. Working around rate limits and permission issues
 * 
 * IMPORTANT: This should only be used for development and testing!
 */

const crypto = require('crypto');
const { v4: uuidv4 } = require('uuid'); 
const jwt = require('jsonwebtoken');
const { supabase, supabaseAdmin } = require('../utils/supabase');

/**
 * Register a new user directly, bypassing Supabase Auth
 */
async function register(req, res) {
  try {
    console.log('🔧 Bypass Auth: Received registration request:', JSON.stringify({
      ...req.body,
      password: '***REDACTED***'
    }, null, 2));
    
    const { username, email, password, publicKey } = req.body;
    
    // Validate input
    if (!username || !email || !password || !publicKey) {
      return res.status(400).json({ 
        success: false, 
        message: 'Please provide username, email, password and publicKey' 
      });
    }
    
    console.log('✅ All required fields provided');
    
    // Check if email already exists in public.users table
    const { data: existingUser, error: checkError } = await supabase
      .from('users')
      .select()
      .eq('email', email)
      .single();
      
    if (existingUser) {
      return res.status(400).json({ 
        success: false, 
        message: 'Email already in use' 
      });
    }
    
    // Generate a UUID for the user (normally Supabase Auth would do this)
    const userId = uuidv4();
    console.log('🆔 Generated user ID:', userId);
    
    // Format public key
    let formattedPublicKey = publicKey;
    if (!formattedPublicKey.startsWith('0x')) {
      formattedPublicKey = '0x' + formattedPublicKey;
    }
    
    // Create user directly in public.users table (bypassing auth.users)
    console.log('🚀 Creating user directly in public.users table');
    
    const userObject = {
      id: userId,
      username,
      email,
      public_key: formattedPublicKey,
      rating: 1200,
      created_at: new Date()
    };
    
    console.log('📝 User object for insertion:', userObject);
    
    // Try to insert using the direct_user_insert function first if available
    try {
      console.log('Attempting to use direct_user_insert function...');
      const { data: rpcData, error: rpcError } = await supabase.rpc('direct_user_insert', {
        user_data: userObject
      });
      
      if (rpcError) {
        console.warn('RPC function failed, falling back to direct insert:', rpcError);
        throw rpcError; // Move to next method
      }
      
      console.log('✅ User created successfully using RPC function:', rpcData);
    } catch (rpcFailure) {
      console.log('Falling back to direct database insertion...');
      
      // Direct insert (only works if demo mode SQL has been applied)
      const { data: insertData, error: insertError } = await supabase
        .from('users')
        .insert([userObject])
        .select();
        
      if (insertError) {
        console.error('❌ Error inserting user:', insertError);
        
        // One final attempt - try disabling RLS via a special header if we have admin access
        if (process.env.SUPABASE_SERVICE_KEY) {
          try {
            const supabaseBypass = supabaseAdmin;
            const { error: bypassError } = await supabaseBypass
              .from('users')
              .insert([userObject]);
              
            if (bypassError) {
              throw bypassError;
            }
          } catch (finalError) {
            console.error('❌ All insertion attempts failed:', finalError);
            return res.status(500).json({ 
              success: false, 
              message: 'Failed to create user. Please check Supabase configuration or run the SQL fixes.' 
            });
          }
        } else {
          return res.status(500).json({ 
            success: false, 
            message: 'Failed to create user. You must run demo_mode_quick_fix.sql or set SUPABASE_SERVICE_KEY.' 
          });
        }
      }
    }
    
    // Generate JWT token for the user
    const token = jwt.sign(
      { id: userId, email, username, publicKey: formattedPublicKey },
      process.env.JWT_SECRET || 'development-secret',
      { expiresIn: '7d' }
    );
    
    // Return success with token
    console.log('🎉 Bypass registration successful for user:', username);
    
    res.status(201).json({
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
    console.error('❌ Bypass registration error:', error);
    res.status(500).json({ 
      success: false, 
      message: 'Server error during registration' 
    });
  }
}

/**
 * Login a user - this still uses Supabase Auth, but has a development fallback
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
    
    // Try normal login first
    const { data: authData, error: authError } = await supabase.auth.signInWithPassword({
      email,
      password
    });
    
    if (!authError) {
      // Normal login successful, get user data and return
      const { data: userData, error: userError } = await supabase
        .from('users')
        .select('*')
        .eq('id', authData.user.id)
        .single();
        
      if (userError) {
        console.error('Error fetching user data:', userError);
        return res.status(500).json({ 
          success: false, 
          message: 'Error fetching user data' 
        });
      }
      
      // Generate JWT token
      const token = jwt.sign(
        { 
          id: userData.id, 
          email: userData.email, 
          username: userData.username,
          publicKey: userData.public_key
        },
        process.env.JWT_SECRET || 'development-secret',
        { expiresIn: '7d' }
      );
      
      // Return success with token
      return res.status(200).json({
        success: true,
        message: 'Login successful',
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
    
    // If normal login failed, try development bypass login
    console.log('Normal login failed, trying bypass login:', authError);
    
    // Look for user directly in the database by email
    const { data: userData, error: userError } = await supabase
      .from('users')
      .select('*')
      .eq('email', email)
      .single();
      
    if (userError || !userData) {
      console.log('User not found in database:', userError);
      return res.status(401).json({ 
        success: false, 
        message: 'Invalid credentials' 
      });
    }
    
    // In development mode, we don't need to check the password
    if (process.env.NODE_ENV === 'development') {
      console.log('Development mode: Bypassing password check!');
      
      // Generate JWT token
      const token = jwt.sign(
        { 
          id: userData.id, 
          email: userData.email, 
          username: userData.username,
          publicKey: userData.public_key
        },
        process.env.JWT_SECRET || 'development-secret',
        { expiresIn: '7d' }
      );
      
      // Return success with token
      return res.status(200).json({
        success: true,
        message: 'Login successful (bypass mode)',
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
    
    // If not in development, return standard error
    return res.status(401).json({ 
      success: false, 
      message: 'Invalid credentials' 
    });
    
  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({ 
      success: false, 
      message: 'Server error during login' 
    });
  }
}

module.exports = {
  register,
  login
};
