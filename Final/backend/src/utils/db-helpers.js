/**
 * Helper function to create a user in the database
 * @param {Object} userData - User data object containing id, username, email, public_key
 * @returns {Promise<Object>} Result of the insertion operation
 */
async function createUserInDatabase(userData) {
  console.log('🔍 Attempting to create user in database:', {
    id: userData.id,
    username: userData.username,
    email: userData.email,
    publicKey: userData.publicKey || userData.public_key
  });

  // Format the public key if needed
  let publicKey = userData.publicKey || userData.public_key;
  if (!publicKey.startsWith('0x')) {
    publicKey = '0x' + publicKey;
  }

  try {
    // First try using the regular client (which would work if RLS policy allows it)
    const { data, error } = await supabase
      .from('users')
      .insert([{
        id: userData.id,
        username: userData.username,
        email: userData.email,
        public_key: publicKey,
        rating: 1200,
        created_at: new Date()
      }])
      .select();

    if (error) {
      console.error('❌ Database insertion error:', error);
      
      // Check if service role key is available
      if (supabaseAdmin) {
        console.log('🔐 Attempting insertion with admin client...');
        
        // Try again with admin client
        const { data: adminData, error: adminError } = await supabaseAdmin
          .from('users')
          .insert([{
            id: userData.id,
            username: userData.username,
            email: userData.email,
            public_key: publicKey,
            rating: 1200,
            created_at: new Date()
          }])
          .select();
          
        if (adminError) {
          console.error('❌ Admin database insertion error:', adminError);
          return { success: false, error: adminError };
        }
        
        console.log('✅ User created with admin client:', adminData);
        return { success: true, data: adminData };
      }
      
      return { success: false, error };
    }
    
    console.log('✅ User created in database:', data);
    return { success: true, data };
  } catch (error) {
    console.error('❌ Exception during user creation:', error);
    return { success: false, error };
  }
}
