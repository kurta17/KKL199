// Simple version of register function that works without admin privileges
async function register(req, res) {
  try {
    console.log('🚀 Received registration request:', JSON.stringify({
      ...req.body,
      password: '***REDACTED***' // Don't log passwords
    }, null, 2));
    
    const { username, email, password, publicKey } = req.body;
    
    // Validate input
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
    
    // Check if user already exists
    const { data: existingUser } = await supabase
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
    
    console.log('Creating auth user with standard signup...');
    const { data: authUser, error: authError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: `${process.env.APP_URL || 'http://localhost:3000'}/email-confirmed`,
        data: {
          username,
          public_key: formattedPublicKey
        }
      }
    });
    
    if (authError) {
      console.error('❌ Error creating auth user:', authError);
      return res.status(500).json({
        success: false,
        message: `Registration failed: ${authError.message}`
      });
    }
    
    console.log('✅ Auth user created:', authUser.user.id);
    
    // IMPORTANT STEP: In regular Supabase signup, we need to confirm the email
    // For development, we'll generate a token and continue without confirmation
    const token = jwt.sign(
      { id: authUser.user.id, email, username, publicKey: formattedPublicKey },
      process.env.JWT_SECRET,
      { expiresIn: '7d' }
    );
    
    // Skip the database insertion for now - user will be created on first login
    // This avoids the foreign key constraint error
    
    console.log('📧 User created but needs email verification');
    console.log('🧪 For development purposes, returning token anyway');
    
    // For development, return success even though email needs verification
    return res.status(200).json({
      success: true,
      message: 'Registration successful. Check your email to confirm your account.',
      token, // Include token for development convenience
      user: {
        id: authUser.user.id,
        username,
        email,
        publicKey: formattedPublicKey
      }
    });
  }
  catch (error) {
    console.error('❌ Registration error:', error);
    return res.status(500).json({
      success: false,
      message: 'Server error during registration'
    });
  }
}
