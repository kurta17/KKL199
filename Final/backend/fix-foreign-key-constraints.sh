#!/bin/bash
# fix-foreign-key-constraints.sh
# This script applies the necessary changes to fix foreign key constraints
# and improve database functionality for the chess app

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Chess App Database Fix Script ===${NC}"
echo -e "${YELLOW}This script will help fix foreign key constraints and database issues${NC}"

# Determine mode - production or demo
read -p "Run in production mode? (y/n, default: n): " production_mode
production_mode=${production_mode:-n}

if [[ $production_mode == "y" || $production_mode == "Y" ]]; then
  echo -e "${GREEN}Running in production mode${NC}"
  echo "This will apply only the necessary fixes while maintaining data integrity"
else
  echo -e "${GREEN}Running in demo mode${NC}"
  echo "This will apply fixes to make the application work without strict database constraints"
fi

# Check for .env file and Supabase URL/Key
if [ ! -f .env ]; then
  echo -e "${RED}Error: .env file not found!${NC}"
  echo "Please create a .env file with SUPABASE_URL and SUPABASE_KEY variables"
  exit 1
fi

# Source .env file
source .env

if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_KEY" ]; then
  echo -e "${RED}Error: Missing Supabase credentials!${NC}"
  echo "Please ensure SUPABASE_URL and SUPABASE_KEY are set in your .env file"
  exit 1
fi

echo -e "${YELLOW}Checking connection to Supabase...${NC}"

# Test connection using curl
response=$(curl -s -o /dev/null -w "%{http_code}" -X GET \
  "$SUPABASE_URL/rest/v1/" \
  -H "apikey: $SUPABASE_KEY")

if [ "$response" != "200" ]; then
  echo -e "${RED}Error: Failed to connect to Supabase!${NC}"
  echo "Please check your SUPABASE_URL and SUPABASE_KEY"
  exit 1
fi

echo -e "${GREEN}Successfully connected to Supabase${NC}"

# Apply SQL fixes
echo -e "${YELLOW}Applying database fixes...${NC}"

# Create a temp file for the SQL
SQL_FILE=$(mktemp)

if [[ $production_mode == "y" || $production_mode == "Y" ]]; then
  # Production mode - apply careful fixes
  cat ./src/db/fix_foreign_key_constraints.sql > $SQL_FILE
  
  # Uncomment the foreign key constraints
  sed -i '' 's/-- ALTER TABLE public.users/ALTER TABLE public.users/g' $SQL_FILE
else
  # Demo mode - apply all fixes including the demo quick fix
  cat ./src/db/demo_mode_quick_fix.sql > $SQL_FILE
fi

# Add database functions
cat ./src/db/database_functions.sql >> $SQL_FILE

# Execute SQL against Supabase
echo -e "${YELLOW}Executing SQL fixes...${NC}"
echo -e "${YELLOW}This may take a moment...${NC}"

# Note: This uses the Supabase database password which may not be available
# You'll need to run this SQL manually in the Supabase dashboard SQL editor
echo -e "${RED}IMPORTANT: You need to manually run the SQL scripts in the Supabase dashboard SQL editor:${NC}"
echo -e "${GREEN}1. Go to Supabase dashboard${NC}"
echo -e "${GREEN}2. Open the SQL Editor${NC}"
echo -e "${GREEN}3. Copy and paste the content of the following files:${NC}"

if [[ $production_mode == "y" || $production_mode == "Y" ]]; then
  echo -e "${YELLOW}   - src/db/fix_foreign_key_constraints.sql${NC}"
else
  echo -e "${YELLOW}   - src/db/demo_mode_quick_fix.sql${NC}"
fi

echo -e "${YELLOW}   - src/db/database_functions.sql${NC}"

# Clean up temp file
rm $SQL_FILE

echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo -e "${YELLOW}Remember to run the SQL scripts in the Supabase dashboard.${NC}"
echo -e "${YELLOW}After running the SQL scripts, restart your application.${NC}"
