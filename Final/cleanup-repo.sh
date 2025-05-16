#!/bin/zsh
# cleanup-repo.sh
# This script organizes the repository by moving non-essential files to a 'legacy' directory

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== REPOSITORY CLEANUP SCRIPT ===${NC}"
echo -e "${YELLOW}This script will move non-essential files to a 'legacy' directory${NC}"
echo

# Create legacy directory if it doesn't exist
if [ ! -d "legacy" ]; then
  mkdir -p legacy
  mkdir -p legacy/docs
  mkdir -p legacy/scripts
  echo -e "${GREEN}Created legacy directories${NC}"
fi

# List of documentation files to move to legacy/docs
docs_to_move=(
  "BYPASS-REGISTRATION-DOCS.md"
  "COMPREHENSIVE-BYPASS-GUIDE.md"
  "DEPLOYMENT.md"
  "README-BYPASS-FIX.md"
  "SUPABASE_SETUP.md"
)

# List of script files to move to legacy/scripts
scripts_to_move=(
  "apply-emergency-sql.sh"
  "apply-rls-policy.sh"
  "check-bypass-route.sh"
  "check-dependencies.sh"
  "commit-game-fixes.sh"
  "debug-dev.sh"
  "emergency-auth-fix.sh"
  "emergency-bypass-fix.sh"
  "fix-all-registration-issues.sh"
  "fix-registration.sh"
  "fix_all_rls_policies.sql"
  "setup-demo.sh"
  "setup-supabase.sh"
  "simple-bypass-fix.sh"
  "test-api-endpoints.sh"
  "test-bypass-endpoint.sh"
  "test-bypass-registration.sh"
  "test-frontend-registration.sh"
)

# Move documentation files
echo -e "${YELLOW}Moving documentation files to legacy/docs...${NC}"
for file in "${docs_to_move[@]}"; do
  if [ -f "$file" ]; then
    mv "$file" legacy/docs/
    echo -e "  ${GREEN}Moved ${file}${NC}"
  else
    echo -e "  ${RED}File not found: ${file}${NC}"
  fi
done

# Move script files
echo -e "${YELLOW}Moving script files to legacy/scripts...${NC}"
for file in "${scripts_to_move[@]}"; do
  if [ -f "$file" ]; then
    mv "$file" legacy/scripts/
    echo -e "  ${GREEN}Moved ${file}${NC}"
  else
    echo -e "  ${RED}File not found: ${file}${NC}"
  fi
done

echo
echo -e "${GREEN}Essential files remaining:${NC}"
echo -e "  - Frontend/ (Main application frontend)"
echo -e "  - backend/ (Backend server code)"
echo -e "  - start-dev.sh (Development server script)"
echo -e "  - monitor-websocket.sh (Connection debugging tool)"
echo -e "  - verify-database.sh (Database validation script)"
echo -e "  - test-two-players.sh (Game testing script)"
echo -e "  - test-game-state.sh (Game state testing script)"
echo -e "  - README.md (Main documentation)"
echo -e "  - CHANGES-SUMMARY.md (Change log)"
echo

echo -e "${YELLOW}Non-essential files have been moved to the legacy directory${NC}"
echo -e "${YELLOW}If you want to ignore the legacy folder entirely, add it to .gitignore${NC}"
