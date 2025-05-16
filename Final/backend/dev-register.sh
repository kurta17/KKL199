#!/bin/bash
# Register a user directly in Supabase database bypassing the API for development
# Usage: ./dev-register.sh <username> <email> <password> <publicKey>

set -e # Exit on error

# Check args
if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <username> <email> <password> <publicKey>"
    exit 1
fi

USERNAME="$1"
EMAIL="$2"
PASSWORD="$3"
PUBLIC_KEY="$4"

# Ensure public key starts with 0x
if [[ ! "$PUBLIC_KEY" =~ ^0x ]]; then
    PUBLIC_KEY="0x$PUBLIC_KEY"
    echo "Added 0x prefix to public key: $PUBLIC_KEY"
fi

# Generate a random UUID for the user
USER_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
echo "Generated user ID: $USER_ID"

echo "Creating user: $USERNAME with email: $EMAIL"
echo "Public Key: $PUBLIC_KEY"

# Base directory
BASE_DIR="$(dirname "$0")"

# Read environment variables from .env file
if [ -f "$BASE_DIR/.env" ]; then
    export $(grep -v '^#' "$BASE_DIR/.env" | xargs)
fi

# Check if we have Supabase credentials
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_KEY" ]; then
    echo "Error: Missing Supabase credentials in .env file"
    exit 1
fi

# Get current timestamp
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Creating user in auth.users table..."
# Not possible without service role key, so we'll skip this step
echo "Please create the user manually in Supabase Auth UI first, then run this script with their user ID"

echo "Inserting user into public.users table..."
# Insert user into public.users table
curl -X POST "$SUPABASE_URL/rest/v1/users" \
    -H "apikey: $SUPABASE_KEY" \
    -H "Authorization: Bearer $SUPABASE_KEY" \
    -H "Content-Type: application/json" \
    -d "{
        \"id\": \"$USER_ID\",
        \"username\": \"$USERNAME\",
        \"email\": \"$EMAIL\",
        \"public_key\": \"$PUBLIC_KEY\",
        \"rating\": 1200,
        \"wins\": 0,
        \"losses\": 0,
        \"draws\": 0,
        \"created_at\": \"$TIMESTAMP\",
        \"updated_at\": \"$TIMESTAMP\"
    }"

echo "User registration complete!"
echo "User ID: $USER_ID"
echo "Username: $USERNAME"
echo "Email: $EMAIL"
echo "Public Key: $PUBLIC_KEY"
