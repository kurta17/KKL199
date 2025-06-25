#!/bin/bash
# verify-database.sh
# This script validates and fixes database schema issues

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== CHESSWEB DATABASE VALIDATION ===${NC}"
echo -e "${YELLOW}This script will validate and fix database schema issues${NC}"
echo

# Check if we have the Supabase URL and key
if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_ANON_KEY" ]; then
  echo -e "${RED}Error: SUPABASE_URL and SUPABASE_ANON_KEY environment variables must be set${NC}"
  echo -e "Please run these commands first:"
  echo -e "${YELLOW}export SUPABASE_URL=your_supabase_url_here${NC}"
  echo -e "${YELLOW}export SUPABASE_ANON_KEY=your_anon_key_here${NC}"
  echo
  # Optionally try to source from .env file
  if [ -f ".env" ]; then
    echo -e "Found .env file, attempting to source it..."
    source .env
  fi
fi

# Function to execute a SQL query
# Usage: execute_query "SQL query"
execute_query() {
  # Use curl to execute the query
  curl -s -X POST \
    "$SUPABASE_URL/rest/v1/rpc/execute_sql" \
    -H "apikey: $SUPABASE_ANON_KEY" \
    -H "Authorization: Bearer $SUPABASE_ANON_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"sql\": \"$1\"}"
}

# Function to check if RPC function exists
function rpc_function_exists() {
  local function_name="$1"
  local result=$(execute_query "SELECT EXISTS(
    SELECT 1 
    FROM pg_proc p 
    JOIN pg_namespace n ON p.pronamespace = n.oid 
    WHERE n.nspname = 'public' AND p.proname = '$function_name'
  )")
  
  if [[ $result == *"true"* ]]; then
    return 0  # Function exists
  else
    return 1  # Function doesn't exist
  fi
}

# Function to create the execute_sql RPC function if it doesn't exist
function create_execute_sql_function() {
  echo -e "${YELLOW}Creating execute_sql RPC function...${NC}"
  
  curl -s -X POST \
    "$SUPABASE_URL/rest/v1/rpc/execute_sql" \
    -H "apikey: $SUPABASE_SERVICE_KEY" \
    -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"sql\": \"
      CREATE OR REPLACE FUNCTION execute_sql(sql text)
      RETURNS json
      LANGUAGE plpgsql
      SECURITY DEFINER
      AS \\$\\$
      DECLARE
        result json;
      BEGIN
        EXECUTE sql INTO result;
        RETURN result;
      EXCEPTION WHEN OTHERS THEN
        RETURN json_build_object('error', SQLERRM);
      END;
      \\$\\$;
    \"}"
    
  echo -e "${GREEN}execute_sql function created or updated.${NC}"
}

# First check if the execute_sql function exists, create it if not
if ! rpc_function_exists "execute_sql"; then
  echo -e "${YELLOW}execute_sql function not found. Creating it...${NC}"
  if [ -z "$SUPABASE_SERVICE_KEY" ]; then
    echo -e "${RED}Error: SUPABASE_SERVICE_KEY environment variable must be set to create the function${NC}"
    echo -e "Please run:"
    echo -e "${YELLOW}export SUPABASE_SERVICE_KEY=your_service_key_here${NC}"
    exit 1
  fi
  create_execute_sql_function
else
  echo -e "${GREEN}execute_sql function already exists.${NC}"
fi

echo -e "${BLUE}1. Checking games table structure...${NC}"
check_result=$(execute_query "SELECT column_name FROM information_schema.columns WHERE table_name = 'games' AND column_name = 'moves'")

# If moves column exists, drop it
if [[ $check_result == *"moves"* ]]; then
  echo -e "${YELLOW}Found 'moves' column in games table. This causes conflicts. Removing it...${NC}"
  execute_query "ALTER TABLE games DROP COLUMN IF EXISTS moves"
  echo -e "${GREEN}Column removed.${NC}"
else
  echo -e "${GREEN}No problematic 'moves' column found.${NC}"
fi

# Check for string_id column, add if missing
echo -e "${BLUE}2. Checking for string_id column in games table...${NC}"
check_result=$(execute_query "SELECT column_name FROM information_schema.columns WHERE table_name = 'games' AND column_name = 'string_id'")
if [[ $check_result != *"string_id"* ]]; then
  echo -e "${YELLOW}Adding string_id column to games table for non-UUID game IDs...${NC}"
  execute_query "ALTER TABLE games ADD COLUMN IF NOT EXISTS string_id TEXT"
  echo -e "${GREEN}Column added.${NC}"
else
  echo -e "${GREEN}string_id column already exists.${NC}"
fi

# Check for moves table and its structure
echo -e "${BLUE}3. Checking moves table structure...${NC}"
check_result=$(execute_query "SELECT table_name FROM information_schema.tables WHERE table_name = 'moves'")
if [[ $check_result != *"moves"* ]]; then
  echo -e "${YELLOW}Creating moves table...${NC}"
  execute_query "CREATE TABLE IF NOT EXISTS moves (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_id UUID REFERENCES games(id),
    move_number INTEGER NOT NULL,
    color TEXT NOT NULL,
    from_square TEXT NOT NULL,
    to_square TEXT NOT NULL,
    fen_after TEXT,
    signature TEXT,
    player_id UUID,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now(),
    piece TEXT,
    promotion TEXT,
    capture BOOLEAN DEFAULT false
  )"
  echo -e "${GREEN}Moves table created.${NC}"
  
  # Create index on game_id
  execute_query "CREATE INDEX IF NOT EXISTS moves_game_id_idx ON moves(game_id)"
  echo -e "${GREEN}Index on game_id created.${NC}"
else
  echo -e "${GREEN}Moves table exists.${NC}"
  
  # Check for required columns in moves table
  for column in "game_id" "move_number" "from_square" "to_square" "fen_after" "signature"; do
    check_result=$(execute_query "SELECT column_name FROM information_schema.columns WHERE table_name = 'moves' AND column_name = '$column'")
    if [[ $check_result != *"$column"* ]]; then
      echo -e "${YELLOW}Adding missing column $column to moves table...${NC}"
      
      # Add column with appropriate type
      case $column in
        "game_id")
          execute_query "ALTER TABLE moves ADD COLUMN IF NOT EXISTS game_id UUID REFERENCES games(id)"
          ;;
        "move_number")
          execute_query "ALTER TABLE moves ADD COLUMN IF NOT EXISTS move_number INTEGER NOT NULL DEFAULT 0"
          ;;
        "from_square"|"to_square"|"fen_after"|"signature")
          execute_query "ALTER TABLE moves ADD COLUMN IF NOT EXISTS $column TEXT"
          ;;
      esac
      echo -e "${GREEN}Column $column added.${NC}"
    fi
  done
fi

# Check for insert_move_safely function
echo -e "${BLUE}4. Checking for insert_move_safely function...${NC}"
if ! rpc_function_exists "insert_move_safely"; then
  echo -e "${YELLOW}Creating insert_move_safely function...${NC}"
  execute_query "CREATE OR REPLACE FUNCTION insert_move_safely(
    game_id UUID,
    move_number INTEGER,
    color TEXT,
    from_square TEXT,
    to_square TEXT,
    fen_after TEXT DEFAULT NULL,
    signature TEXT DEFAULT NULL,
    player_id UUID DEFAULT NULL,
    timestamp TIMESTAMPTZ DEFAULT now(),
    piece TEXT DEFAULT NULL,
    promotion TEXT DEFAULT NULL,
    capture BOOLEAN DEFAULT false
  ) RETURNS SETOF moves AS $$
  BEGIN
    RETURN QUERY
    INSERT INTO moves (
      game_id, move_number, color, from_square, to_square,
      fen_after, signature, player_id, timestamp, piece, promotion, capture
    )
    VALUES (
      game_id, move_number, color, from_square, to_square,
      fen_after, signature, player_id, timestamp, piece, promotion, capture
    )
    RETURNING *;
  EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'Error inserting move: %', SQLERRM;
    RETURN;
  END;
  $$ LANGUAGE plpgsql SECURITY DEFINER;"
  echo -e "${GREEN}insert_move_safely function created.${NC}"
else
  echo -e "${GREEN}insert_move_safely function exists.${NC}"
fi

# Check for game state consistency
echo -e "${BLUE}5. Scanning database for game state inconsistencies...${NC}"
inconsistent_games=$(execute_query "
SELECT g.id, g.white_player_id, g.black_player_id, 
  (SELECT COUNT(*) FROM moves m WHERE m.game_id = g.id) AS move_count
FROM games g 
WHERE g.status = 'completed' AND NOT EXISTS (
  SELECT 1 FROM moves m WHERE m.game_id = g.id
)
LIMIT 10")

if [[ $inconsistent_games == *"move_count"* ]]; then
  echo -e "${YELLOW}Found games with inconsistent state. Here's a sample:${NC}"
  echo "$inconsistent_games" | grep -o '{.*}'
  echo -e "${YELLOW}Would you like to mark these games as 'corrupted'? (y/n)${NC}"
  read answer
  if [[ $answer == "y" || $answer == "Y" ]]; then
    execute_query "UPDATE games SET status = 'corrupted' WHERE status = 'completed' AND NOT EXISTS (SELECT 1 FROM moves m WHERE m.game_id = games.id)"
    echo -e "${GREEN}Inconsistent games marked as 'corrupted'.${NC}"
  else
    echo -e "${BLUE}No changes made to inconsistent games.${NC}"
  fi
else
  echo -e "${GREEN}No game state inconsistencies found.${NC}"
fi
fi

echo -e "${BLUE}2. Checking RPC functions...${NC}"
check_rpc=$(execute_query "SELECT proname FROM pg_proc WHERE proname = 'safely_create_game'")

# If the RPC function doesn't exist, create it
if [[ $check_rpc != *"safely_create_game"* ]]; then
  echo -e "${YELLOW}RPC function 'safely_create_game' not found. Creating it...${NC}"
  
  execute_query "CREATE OR REPLACE FUNCTION public.safely_create_game(
    game_id UUID, 
    white_id UUID,
    black_id UUID,
    game_status TEXT,
    game_result JSONB
  ) RETURNS UUID AS $$
  BEGIN
    INSERT INTO games (id, white_player_id, black_player_id, status, result, created_at, started_at, completed_at)
    VALUES (game_id, white_id, black_id, game_status, game_result, NOW(), NOW(), NOW());
    RETURN game_id;
  EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Error creating game: %', SQLERRM;
    RETURN NULL;
  END;
  $$ LANGUAGE plpgsql SECURITY DEFINER;"
  
  echo -e "${GREEN}RPC function created.${NC}"
else
  echo -e "${GREEN}RPC function 'safely_create_game' already exists.${NC}"
fi

echo -e "${BLUE}3. Testing game creation and move storage...${NC}"
# Create a test game
test_game_id=$(execute_query "SELECT safely_create_game('00000000-0000-0000-0000-000000000001'::uuid, 
  (SELECT id FROM users LIMIT 1), 
  (SELECT id FROM users ORDER BY id DESC LIMIT 1), 
  'completed', 
  '{\"winner\":\"white\",\"reason\":\"checkmate\"}'::jsonb)")

echo -e "${GREEN}Database schema verification complete.${NC}"
echo -e "${YELLOW}If you still experience issues, check the Supabase Console for more details.${NC}"
