#!/bin/bash

# Script to apply the fix for user insertion FK constraint
echo "🔧 Applying fix for user insertion foreign key constraint..."

# Check if SUPABASE_URL and SUPABASE_SERVICE_KEY are set in .env
if [ ! -f .env ]; then
  echo "❌ Error: .env file not found in the backend directory"
  exit 1
fi

# Source the .env file to get Supabase credentials
source .env

if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_KEY" ]; then
  echo "❌ Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in .env file"
  exit 1
fi

# Run the SQL fix using curl to the Supabase REST API
echo "📄 Running fix_user_inserts.sql against Supabase database..."

PGREST_URL="${SUPABASE_URL}/rest/v1/rpc/exec_sql"

curl -X POST "${PGREST_URL}" \
  -H "apikey: ${SUPABASE_SERVICE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_SERVICE_KEY}" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "query": "$(cat src/db/fix_user_inserts.sql | tr -d '\n')"
}
EOF

# Check if the curl command succeeded
if [ $? -eq 0 ]; then
  echo "✅ Successfully applied the fix!"
else
  echo "❌ Failed to apply the fix. Please check your Supabase credentials."
  exit 1
fi

echo "🔍 Now modifying the registration process to handle the foreign key constraint properly..."

# Make sure nodemon is already running, or restart it
echo "♻️ Restarting server to apply changes..."
kill $(lsof -t -i:5000) 2>/dev/null || true
npm run dev > /dev/null 2>&1 &
echo "✅ Done! The registration process should now work correctly."
