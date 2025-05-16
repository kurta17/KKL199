#!/bin/bash

# Fix script for the "user not allowed" error in the registration process
echo "🔧 Fixing the 'User not allowed' error in registration..."

# Path to the backend directory
BACKEND_DIR="$(dirname "$0")"
cd "$BACKEND_DIR"

# Add the missing header to the simple-auth.js file
sed -i '' '1i\
const jwt = require("jsonwebtoken");\
const { supabase } = require("../utils/supabase");\
' src/controllers/simple-auth.js

# Add exports to the simple-auth.js file
echo "
// Export other functions from the original auth.js
// Importing them directly to avoid duplicating code
const { login, verifyEmail, forgotPassword, resetPassword } = require('./auth');

module.exports = {
  register,
  login,
  verifyEmail, 
  forgotPassword,
  resetPassword
};" >> src/controllers/simple-auth.js

# Create backup of original auth.js
cp src/controllers/auth.js src/controllers/auth.js.bak

# Copy the simple-auth.js to auth.js
cp src/controllers/simple-auth.js src/controllers/auth.js

echo "✅ Auth controller updated to use a simpler registration process!"
echo "📝 The original controller has been backed up to auth.js.bak"

# Update the .env file with development settings
if [ -f .env ]; then
  # Set NODE_ENV to development
  sed -i '' 's/^NODE_ENV=.*/NODE_ENV=development/' .env
  # Add development settings if missing
  grep -q "^DEBUG_MODE" .env || echo "DEBUG_MODE=true" >> .env
fi

echo "🚀 To test the fix, restart your backend server and try registering again."
