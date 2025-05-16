# WebSocket Connection Debugging Guide

This document provides troubleshooting steps for the cross-browser WebSocket connection issue in the ChessChain application.

## Issue Description

When running the chess application with different browsers (Chrome and Safari), users aren't consistently being matched together via the WebSocket-based matchmaking system. This issue is particularly problematic for cross-browser testing.

## Root Cause Analysis

The primary issue was identified in the WebSocket connection code in `Frontend/chess-website/src/services/api.js`:

```javascript
this.socket = new WebSocket('ws://localhost:5000');
```

This hardcoded WebSocket URL uses `localhost`, which can be problematic when:
1. Different browsers may handle `localhost` domain resolution differently 
2. Some browsers might apply different security policies to WebSocket connections
3. The connection doesn't adapt to different environments or hostnames

## Applied Fix

The WebSocket connection code has been updated to use dynamic hostname detection:

```javascript
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const hostname = window.location.hostname;
const wsUrl = `${protocol}//${hostname}:5000`;
console.log(`Connecting to WebSocket at ${wsUrl}`);
this.socket = new WebSocket(wsUrl);
```

This change ensures that:
1. The WebSocket connection uses the same hostname as the current page
2. The protocol (ws/wss) matches the security of the page (http/https)
3. Connection details are properly logged for debugging

## Additional Debugging Tools

We've added several new tools to help diagnose WebSocket connection issues:

### 1. WebSocket Debug Panel

Access the debug panel by adding `?debug=websocket` to the URL in your browser, e.g.:
```
http://localhost:3000/game?debug=websocket
```

The panel shows:
- Connection status
- WebSocket URL
- User ID
- Game ID
- Browser information
- Connection attempts

### 2. Test WebSocket Connection Script

Run the new test script:
```bash
./test-websocket-connection.sh
```

This script:
- Opens Chrome and Safari browsers with the WebSocket debug panel enabled
- Provides instructions for checking the connection status
- Makes it easy to see if both browsers are connecting to the same WebSocket URL

### 3. Matchmaking Monitor

Run the new matchmaking monitor:
```bash
./monitor-matchmaking.sh
```

This tool:
- Monitors the backend logs for matchmaking-related events
- Shows when users join the queue
- Displays attempted matches between users
- Helps identify if users from different browsers are being considered for matching

## Testing the Fix

1. Run the WebSocket connection test:
   ```bash
   ./test-websocket-connection.sh
   ```

2. Log in to both browsers and check the console/debug panel to ensure they're connecting to the same WebSocket URL

3. Monitor the matchmaking process:
   ```bash
   ./monitor-matchmaking.sh
   ```

4. Verify that users from both browsers appear in the matchmaking queue and get matched together

## Troubleshooting Steps

If matchmaking issues persist:

1. Check that both browsers are connecting to the same WebSocket URL
   - Look at the "WebSocket URL" in the debug panel

2. Ensure both users are properly authenticated
   - Check the "User ID" in the debug panel
   - Look for "authenticated" messages in the backend logs

3. Verify both users are joining the queue
   - Look for "joined matchmaking queue" messages in the logs

4. Watch for potential timing issues
   - The first user might be removed from the queue if the matchmaking check runs before the second user joins

5. Examine browser console logs for any errors or warnings
   - Security policies
   - Connection failures
   - Authentication issues

6. Try using the same browser type for both users as a test
   - If this works but cross-browser still fails, it may indicate a browser-specific issue
