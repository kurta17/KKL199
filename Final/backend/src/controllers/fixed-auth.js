// Updated Auth Controller with fixed registration logic
const jwt = require('jsonwebtoken');
const { ethers } = require('ethers');
const { supabase, supabaseAdmin } = require('../utils/supabase');
const { verifySignature } = require('../utils/blockchain');

/**
 * Register a new user - Fixed version to handle foreign key constraint
 */
async function register(req, res) {
  try {
    console.log('🚀 Received registration request:', JSON.stringify({
      ...req.body,
      password: '***REDACTED***' // Don't log passwords
    }, null, 2));
    
    const { username, email, password, publicKey } = req.body;
    
    // Validate input
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
    
    // Format public key properly
    let formattedPublicKey = publicKey;
    if (!formattedPublicKey.startsWith('0x')) {
      formattedPublicKey = '0x' + formattedPublicKey;
      console.log('Added 0x prefix to public key:', formattedPublicKey);
    }
    
    // Check if email already exists
    const { data: existingUser } = await supabaseAdmin
      .from('users')
      .select('email')
      .eq('email', email)
      .maybeSingle();
      
    if (existingUser) {
      return res.status(400).json({ 
        success: false, 
        message: 'Email already in use' 
      });
    }

    console.log('📝 Creating user in Supabase Auth with admin client...');
    
    // Step 1: Create the user in auth.users with admin powers
    const { data: authUser, error: authError } = await supabaseAdmin.auth.admin.createUser({
      email,
      password,
      email_confirm: true, // Auto-confirm the email
      user_metadata: {
        username,
        public_key: formattedPublicKey
      }
    });
    
    if (authError) {
      console.error('❌ Error creating auth user:', authError);
      return res.status(500).json({
        success: false,
        message: `Error creating user: ${authError.message}`
      });
    }
    
    console.log('✅ Auth user created successfully:', authUser.user.id);
    
    // Small delay to ensure the auth user is propagated in the database
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // Step 2: Insert the user into public.users table
    console.log('📝 Adding user to users table...');
    const userObject = { 
      id: authUser.user.id, // This must match the ID in auth.users
      username,
      email,
      public_key: formattedPublicKey,
      rating: 1200,
      created_at: new Date()
    };
    
    console.log('User object:', userObject);
    
    const { data: newUser, error: insertError } = await supabaseAdmin
      .from('users')
      .insert([userObject])
      .select();
      
    if (insertError) {
      console.error('❌ Error inserting user data:', insertError);
      console.error('Error details:', {
        code: insertError.code,
        message: insertError.message,
        details: insertError.details
      });
      
      // Try to clean up the auth user if possible
      try {
        await supabaseAdmin.auth.admin.deleteUser(authUser.user.id);
        console.log('🗑️ Cleaned up auth user after failed insertion');
      } catch (cleanupError) {
        console.error('Failed to clean up auth user:', cleanupError);
      }
      
      if (insertError.code === '23503') {
        return res.status(500).json({
          success: false,
          message: 'Foreign key constraint error. The auth user ID is not being properly created.'
        });
      }
      
      return res.status(500).json({ 
        success: false, 
        message: 'Database error creating user profile' 
      });
    }
    
    console.log('✅ User added to database successfully!');
    
    // Step 3: Create a session for the new user
    const { data: session, error: sessionError } = await supabaseAdmin.auth.admin.generateLink({
      type: 'magiclink',
      email: email
    });
    
    if (sessionError) {
      console.error('❌ Error generating session:', sessionError);
      // Continue anyway, we'll create a JWT token manually
    }
    
    // Step 4: Generate a JWT token for the user
    const token = jwt.sign(
      { 
        id: authUser.user.id, 
        email, 
        username,
        publicKey: formattedPublicKey
      },
      process.env.JWT_SECRET || 'fallback-secret-key-for-development',
      { expiresIn: '7d' }
    );
    
    // Return success with token
    console.log('🎉 Registration successful!');
    return res.status(201).json({
      success: true,
      message: 'Registration successful',
      token,
      user: {
        id: authUser.user.id,
        username,
        email,
        publicKey: formattedPublicKey
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

// Keep existing login function and other functions
// ...

module.exports = {
  register,
  // Include other exported functions
};
