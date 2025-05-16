const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const cors = require('cors');
const dotenv = require('dotenv');
const { setupWebSocket } = require('./utils/websocket');
const { startBlockchainNode } = require('./services/blockchain-bridge');

// Load environment variables
dotenv.config();

// Import routes
const authRoutes = require('./routes/auth');
const gameRoutes = require('./routes/game');
const blockchainRoutes = require('./routes/blockchain');

// Development routes (these should not be included in production)
const devRoutes = require('./routes/dev');
let bypassRoutes;
try {
  bypassRoutes = require('./routes/bypass');
  console.log('✅ Loaded bypass routes for development use');
} catch (error) {
  console.log('Bypass routes not available:', error.message);
}
console.log('Loaded dev routes:', typeof devRoutes);

// Create Express app
const app = express();
const server = http.createServer(app);

// Middleware
app.use(cors());
app.use(express.json());

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    timestamp: new Date().toISOString(),
    supabase: process.env.SUPABASE_URL ? 'configured' : 'missing'
  });
});

// Start blockchain node
console.log('Starting blockchain node...');
startBlockchainNode()
  .then((success) => {
    console.log(success ? '✅ Blockchain node started successfully' : '❌ Failed to start blockchain node');
  })
  .catch(err => {
    console.error('Error starting blockchain node:', err);
  });

// WebSocket server
const wss = new WebSocket.Server({ server });
setupWebSocket(wss);

// Routes
app.use('/api/auth', authRoutes);
app.use('/api/game', gameRoutes);
app.use('/api/blockchain', blockchainRoutes);

// Development routes - only in development environment
if (process.env.NODE_ENV !== 'production') {
  app.use('/api/dev', devRoutes);
  
  // Add bypass routes for easier development
  if (bypassRoutes) {
    app.use('/api/bypass', bypassRoutes);
    console.log('🛠️ Bypass routes enabled at /api/bypass - USE ONLY FOR DEVELOPMENT');
  }
  
  console.log('🔧 Development routes enabled');
}

// Root route
app.get('/', (req, res) => {
  res.send('ChainChess Backend API');
});

// Start server
const PORT = process.env.PORT || 5000;
server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
