const { createClient } = require('@supabase/supabase-js');
const dotenv = require('dotenv');

dotenv.config();

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY; // Get service role key

if (!supabaseUrl || !supabaseKey) {
  console.error('Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_KEY in .env file');
  process.exit(1);
}

// Log warning if service key is missing
if (!supabaseServiceKey) {
  console.warn('⚠️ SUPABASE_SERVICE_KEY is not set. Admin operations will not work.');
  console.warn('Please set SUPABASE_SERVICE_KEY in your .env file to enable admin operations.');
}

// Creating client with standard anon key for normal operations
const supabase = createClient(supabaseUrl, supabaseKey);

// Creating admin client with service role for operations that need elevated privileges
const supabaseAdmin = createClient(
  supabaseUrl,
  supabaseServiceKey || supabaseKey, // Fallback to anon key if service key not available
  {
    auth: {
      autoRefreshToken: false,
      persistSession: false
    },
    global: {
      headers: {
        'X-Client-Info': 'supabase-js-server',
      },
    }
  }
);

module.exports = { 
  supabase, 
  supabaseAdmin
};
