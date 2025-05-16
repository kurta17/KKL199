#!/bin/zsh
# commit-changes.sh
# Script to commit the game state synchronization fixes

# Add all essential files and directories
echo "Adding essential files to commit..."

# Add the frontend and backend directories
git add Frontend/ backend/

# Add essential scripts
git add start-dev.sh monitor-websocket.sh verify-database.sh
git add test-two-players.sh test-game-state.sh 

# Add documentation and configuration
git add CHANGES-SUMMARY.md README.md .gitignore
git add cleanup-repo.sh

# Add package.json
git add package.json

# Commit with a descriptive message
git commit -m "Fix game state synchronization issues

- Fixed board rotation issues during two-player matches
- Fixed opponent name and rating display instead of 'unknown'
- Improved game state synchronization between browsers
- Fixed database storage for game data
- Enhanced WebSocket connection stability
- Added database verification and testing scripts
- Cleaned up repository structure by moving legacy files"

echo "Changes committed successfully! Use 'git push origin main' to upload to your repository."
