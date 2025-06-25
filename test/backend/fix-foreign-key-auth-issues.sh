#!/bin/bash
# fix-foreign-key-auth-issues.sh
# This script applies all necessary fixes for the foreign key constraint issues
# in the user registration and game saving processes

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Chess App Foreign Key Constraint Fix ===${NC}"
echo -e "${YELLOW}This script will apply all necessary fixes to resolve foreign key constraint violations${NC}"

# Check for .env file
if [ ! -f .env ]; then
  echo -e "${RED}Error: .env file not found!${NC}"
  echo "Please create a .env file with SUPABASE_URL and SUPABASE_KEY variables"
  exit 1
fi

# Source the .env file to get credentials
source .env

# Validate Supabase credentials
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_KEY" ]; then
  echo -e "${RED}Error: Missing Supabase credentials!${NC}"
  echo "Please ensure SUPABASE_URL and SUPABASE_KEY are set in your .env file"
  exit 1
fi

echo -e "${YELLOW}Starting fix process...${NC}"

# Create temp directory for SQL files
TEMP_DIR=$(mktemp -d)
SQL_FILE="$TEMP_DIR/complete_fix.sql"

# Create a combined SQL file with all fixes
echo -e "${YELLOW}Creating SQL fix file...${NC}"

echo "-- Complete fix for foreign key constraint issues" > $SQL_FILE
echo "-- Generated $(date)" >> $SQL_FILE
echo "" >> $SQL_FILE

# Append each SQL fix file
cat ./src/db/fix_user_foreign_key.sql >> $SQL_FILE
echo "" >> $SQL_FILE
cat ./src/db/direct_user_insert.sql >> $SQL_FILE
echo "" >> $SQL_FILE
cat ./src/db/database_functions.sql >> $SQL_FILE
echo "" >> $SQL_FILE

# If in development mode, also apply the demo mode quick fix
read -p "Apply demo mode fixes? (y/n, default: y): " demo_mode
demo_mode=${demo_mode:-y}

if [[ $demo_mode == "y" || $demo_mode == "Y" ]]; then
  echo -e "${YELLOW}Including demo mode fixes...${NC}"
  cat ./src/db/demo_mode_quick_fix.sql >> $SQL_FILE
fi

echo -e "${GREEN}Generated SQL fix file${NC}"

# Instructions for the user
echo -e "${RED}IMPORTANT: You need to manually run the SQL in the Supabase dashboard:${NC}"
echo -e "${GREEN}1. Go to your Supabase dashboard${NC}"
echo -e "${GREEN}2. Open the SQL Editor${NC}"
echo -e "${GREEN}3. Copy and paste the SQL from: $SQL_FILE${NC}"
echo -e "${GREEN}4. Execute the SQL${NC}"

# Copy SQL to clipboard if on macOS
if [ "$(uname)" == "Darwin" ]; then
  if command -v pbcopy > /dev/null; then
    cat $SQL_FILE | pbcopy
    echo -e "${GREEN}✅ SQL copied to clipboard!${NC}"
  fi
fi

echo ""
echo -e "${YELLOW}After running the SQL, restart your server for the changes to take effect${NC}"
echo -e "${GREEN}Fix completed - follow the instructions above to apply the database changes${NC}"
