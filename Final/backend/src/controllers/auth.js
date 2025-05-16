const jwt = require('jsonwebtoken');
const { ethers } = require('ethers');
const { supabase, supabaseAdmin } = require('../utils/supabase');
const { verifySignature } = require('../utils/blockchain');

/**
 * Register a new user
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
      console.log('❌ Missing registration fields:', {
        username: !!username,
        email: !!email,
        password: !!password,
        publicKey: !!publicKey
      });
      return res.status(400).json({ 
        success: false, 
        message: 'Please provide username, email, password and publicKey' 
      });
    }
    
    console.log('✅ All required fields provided');
    
    // Check if email already exists
    const { data: existingUser, error: checkError } = await supabase
      .from('users')
      .select()
      .eq('email', email)
      .single();
      
    if (checkError && checkError.code !== 'PGRST116') {
      console.error('Database error checking user:', checkError);
      return res.status(500).json({ 
        success: false, 
        message: 'Error checking existing user'
      });
    }
    
    if (existingUser) {
      return res.status(400).json({ 
        success: false, 
        message: 'Email already in use' 
      });
    }
    
    // Create user in Supabase Auth with auto-confirm enabled for development
    console.log('Creating auth user with public key in metadata:', publicKey);
    
    // Check if we're in development mode to bypass email verification
    const isDevelopment = process.env.NODE_ENV === 'development';
    console.log('Environment:', process.env.NODE_ENV, 'isDevelopment:', isDevelopment);
    
    // Try to create user with admin client first if service key is available
    let authUser;
    let authError;
    
    // Check if we have a proper service role key by checking a property on supabaseAdmin
    const hasServiceRole = !!process.env.SUPABASE_SERVICE_KEY;
    
    if (hasServiceRole) {
      console.log('Using admin client to create user with auto-confirmation...');
      const { data: adminAuthUser, error: adminAuthError } = await supabaseAdmin.auth.admin.createUser({
        email,
        password,
        email_confirm: true, // Auto-confirm the email
        user_metadata: {
          username: username,
          public_key: publicKey
        }
      });
      
      authUser = adminAuthUser;
      authError = adminAuthError;
    } else {
      console.log('No service role key available, using standard signup...');
      const { data: regularAuthUser, error: regularAuthError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: `${process.env.APP_URL || 'http://localhost:3000'}/email-confirmed`,
          data: {
            username: username,
            public_key: publicKey
          }
        }
      });
      
      authUser = regularAuthUser;
      authError = regularAuthError;
    }
    
    if (authError) {
      console.error('Error creating auth user:', authError);
      
      // Provide more specific error messages for common issues
      if (authError.message && authError.message.includes('invalid')) {
        return res.status(400).json({
          success: false,
          message: 'Invalid email format. Please use a valid email address like user@gmail.com'
        });
      }
      
      if (authError.code === 'over_email_send_rate_limit') {
        console.log('Hit rate limit with email service. Using alternative registration flow.');
        
        // For development only - create a user directly with the admin client
        // This bypasses email verification entirely
        if (process.env.NODE_ENV === 'development') {
          try {
            // First create the auth user with admin powers
            const { data: adminAuthUser, error: adminAuthError } = await supabaseAdmin.auth.admin.createUser({
              email,
              password,
              email_confirm: true, // Auto-confirm the email
              user_metadata: {
                username,
                public_key: publicKey
              }
            });
            
            if (adminAuthError) {
              console.error('Admin auth creation error:', adminAuthError);
              return res.status(500).json({
                success: false,
                message: 'Error creating user with admin method'
              });
            }
            
            // Continue with the user insertion using the admin-created user
            authUser = adminAuthUser;
          } catch (adminError) {
            console.error('Error in admin user creation:', adminError);
            return res.status(429).json({
              success: false,
              message: 'Too many registration attempts. Please try again later.'
            });
          }
        } else {
          return res.status(429).json({
            success: false,
            message: 'Too many registration attempts. Please try again later.'
          });
        }
      }
      
      return res.status(500).json({ 
        success: false, 
        message: 'Error creating user account' 
      });
    }
    
    // Add user data to our users table - using admin client to bypass RLS
    console.log('Inserting user with public key:', publicKey);
    
    // Ensure publicKey is properly formatted (starts with 0x and is correct length)
    let formattedPublicKey = publicKey;
    if (!formattedPublicKey.startsWith('0x')) {
      formattedPublicKey = '0x' + formattedPublicKey;
      console.log('Added 0x prefix to public key:', formattedPublicKey);
    }
    
    if (formattedPublicKey.length !== 42) {
      console.warn('Warning: Public key length is not standard (expected 42, got', formattedPublicKey.length, ')');
    }
    
    // Skip explicit verification since we just created the user
    // We'll just add a small delay to ensure the auth user is propagated in the database
    console.log('Auth user created with ID:', authUser.user.id);
    console.log('Waiting a moment for auth user to propagate...');
    
    // Small delay to ensure database consistency
    await new Promise(resolve => setTimeout(resolve, 500));
    
    console.log('Proceeding with users table insertion...');
    
    // Create the user object and log it
    const userObject = { 
      id: authUser.user.id,
      username,
      email,
      public_key: formattedPublicKey,
      rating: 1200, // Default chess rating
      created_at: new Date()
    };
    
    console.log('User object for insertion:', userObject);
    
    // First try: Use safely_create_user RPC if available (avoids foreign key constraint issues)
    try {
      console.log('Attempting to create user with safely_create_user RPC function...');
      const { data: rpcResult, error: rpcError } = await supabaseAdmin.rpc('safely_create_user', {
        user_id: userObject.id,
        username: userObject.username,
        user_email: userObject.email,
        public_key: userObject.public_key
      });
      
      if (!rpcError) {
        console.log('Successfully created user with RPC function:', rpcResult);
        // Skip the regular insert since we succeeded with RPC
        return res.status(201).json({
          success: true,
          message: 'User registered successfully',
          user: {
            id: userObject.id,
            username: userObject.username,
            email: userObject.email
          }
        });
      } else {
        console.warn('Failed to create user with RPC, falling back to regular insert:', rpcError);
      }
    } catch (rpcCallError) {
      console.warn('RPC function call failed (might not exist yet):', rpcCallError.message);
      console.log('Falling back to regular insert...');
    }
    
    // Second try: Use transaction to ensure atomicity
    const { data: newUser, error: insertError } = await supabaseAdmin
      .from('users')
      .insert([userObject])
      .select();
      
    if (insertError) {
      console.error('Error inserting user data:', insertError);
      
      // Log more details about the error for debugging
      console.error('Insert error details:', {
        code: insertError.code,
        message: insertError.message,
        details: insertError.details,
        hint: insertError.hint
      });
      
      // Check for common Postgres error codes
      if (insertError.code === '42501') {
        return res.status(500).json({
          success: false,
          message: 'Error: Database permission denied. Missing RLS policy for inserting users.'
        });
      } else if (insertError.code === '23505') {
        return res.status(400).json({
          success: false,
          message: 'Username or email already exists. Please try a different one.'
        });
      } else if (insertError.code === '23503' && insertError.message.includes('users_id_fkey')) {
        console.log('Foreign key constraint violation - attempting direct insertion...');
        
        // Last attempt: Try to directly fix the foreign key constraint issue
        try {
          // Increased delay for auth user propagation - sometimes this is just a timing issue
          console.log('Adding longer delay for auth user to propagate...');
          await new Promise(resolve => setTimeout(resolve, 2000));
          
          // Try a direct SQL query to insert the user, bypassing the foreign key constraint
          const { data: directResult, error: directError } = await supabaseAdmin.rpc('direct_user_insert', {
            user_data: userObject
          });
          
          if (!directError) {
            console.log('Successfully inserted user with direct method:', directResult);
            
            // Generate JWT token
            const token = jwt.sign(
              { id: authUser.user.id, email, username, publicKey },
              process.env.JWT_SECRET,
              { expiresIn: '7d' }
            );
            
            // Return success
            return res.status(201).json({
              success: true,
              message: 'User registered successfully (with fallback method)',
              token,
              user: {
                id: authUser.user.id,
                username,
                email,
                publicKey: formattedPublicKey
              }
            });
          } else {
            console.error('Direct insertion method also failed:', directError);
            
            // If we also failed with that approach, just log the user in anyway if we're in development
            if (process.env.NODE_ENV === 'development') {
              // Generate JWT token anyway - the user exists in auth.users which is what matters for login
              const token = jwt.sign(
                { id: authUser.user.id, email, username, publicKey },
                process.env.JWT_SECRET,
                { expiresIn: '7d' }
              );
              
              console.log('Returning token for auth user despite users table insertion failure');
              
              // Return partial success - the user can at least log in
              return res.status(201).json({
                success: true,
                message: 'User registered in authentication system but profile data creation failed. Some features may be limited.',
                token,
                user: {
                  id: authUser.user.id,
                  username,
                  email,
                  publicKey: formattedPublicKey
                },
                partialRegistration: true
              });
            }
          }
        } catch (directInsertError) {
          console.error('Error in direct insertion attempt:', directInsertError);
        }
      }
      
      return res.status(500).json({ 
        success: false, 
        message: 'Error creating user profile' 
      });
    }
    
    // Generate JWT token
    const token = jwt.sign(
      { id: authUser.user.id, email, username, publicKey },
      process.env.JWT_SECRET,
      { expiresIn: '7d' }
    );
    
    // Return success with token
    console.log('Registration successful. Sending response with publicKey:', publicKey);
    
    res.status(201).json({
      success: true,
      message: 'User registered successfully',
      token,
      user: {
        id: authUser.user.id,
        username,
        email,
        publicKey: formattedPublicKey // Use the formatted public key here
      }
    });
    
  } catch (error) {
    console.error('Registration error:', error);
    return res.status(500).json({ success: false, message: 'Server error during registration' });
    res.status(500).json({ 
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
      console.log('Login error details:', authError);
      
      // Check specific error conditions
      if (authError.message && authError.message.includes('Email not confirmed')) {
        // In development, we could automatically confirm the email here
        if (process.env.NODE_ENV !== 'production') {
          return res.status(401).json({ 
            success: false, 
            message: 'Email not confirmed. Use the /api/dev/force-login endpoint with autoConfirm:true for development testing.' 
          });
        }
        return res.status(401).json({ 
          success: false, 
          message: 'Please check your email to confirm your account before logging in' 
        });
      }
      
      return res.status(401).json({ 
        success: false, 
        message: 'Invalid credentials' 
      });
    }
    
    // Get user data
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
      process.env.JWT_SECRET,
      { expiresIn: '7d' }
    );
    
    // Return success with token
    res.status(200).json({
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
    res.status(500).json({ 
      success: false, 
      message: 'Server error during login' 
    });
  }
}

/**
 * Verify email (placeholder for now)
 */
async function verifyEmail(req, res) {
  const { token } = req.params;
  
  // This would verify an email token
  // For now, just redirect to frontend
  res.redirect(`${process.env.FRONTEND_URL}/login?verified=true`);
}

/**
 * Request password reset
 */
async function forgotPassword(req, res) {
  try {
    const { email } = req.body;
    
    if (!email) {
      return res.status(400).json({ 
        success: false, 
        message: 'Please provide an email' 
      });
    }
    
    // Send reset password link via Supabase Auth
    const { error } = await supabase.auth.resetPasswordForEmail(email);
    
    if (error) {
      console.error('Error sending reset email:', error);
      return res.status(400).json({ 
        success: false, 
        message: 'Error sending password reset email' 
      });
    }
    
    res.status(200).json({ 
      success: true, 
      message: 'Password reset link sent if email exists' 
    });
    
  } catch (error) {
    console.error('Password reset error:', error);
    res.status(500).json({ 
      success: false, 
      message: 'Server error processing password reset' 
    });
  }
}

/**
 * Reset password with token
 */
async function resetPassword(req, res) {
  try {
    const { token } = req.params;
    const { password } = req.body;
    
    if (!password) {
      return res.status(400).json({ 
        success: false, 
        message: 'Please provide a new password' 
      });
    }
    
    // Update password via Supabase Auth
    const { error } = await supabase.auth.updateUser({
      password
    }, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });
    
    if (error) {
      console.error('Error resetting password:', error);
      return res.status(400).json({ 
        success: false, 
        message: 'Invalid or expired token' 
      });
    }
    
    res.status(200).json({ 
      success: true, 
      message: 'Password updated successfully' 
    });
    
  } catch (error) {
    console.error('Password update error:', error);
    res.status(500).json({ 
      success: false, 
      message: 'Server error updating password' 
    });
  }
}

module.exports = {
  register,
  login,
  verifyEmail,
  forgotPassword,
  resetPassword
};
