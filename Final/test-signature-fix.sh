#!/bin/bash
# Test script for verifying the signature verification fix

echo "🧪 Testing Ed25519 signature verification fix..."

# Step 1: Install required packages
echo "🔧 Installing required packages..."
cd /Users/levandalbashvili/Documents/GitHub/KKL199/Final/Frontend/chess-website
npm install tweetnacl base64-js

# Step 2: Generate test keypairs
echo "🔑 Generating test keypairs..."
cd /Users/levandalbashvili/Documents/GitHub/KKL199/Final
./generate-test-keys.sh

# Step 3: Start backend in development mode (background)
echo "🚀 Starting backend server..."
cd /Users/levandalbashvili/Documents/GitHub/KKL199/Final/backend
npm run dev & 
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

# Wait for backend to initialize
sleep 5

# Step 4: Run a simple signature verification test
echo "🔍 Testing signature verification..."
cd /Users/levandalbashvili/Documents/GitHub/KKL199/Final
source test_keypairs.txt
node -e "
const nacl = require('tweetnacl');
const base64js = require('base64-js');
const axios = require('axios');

async function testSignature() {
  try {
    // Convert base64 keys to Uint8Array
    const publicKeyBytes = base64js.toByteArray('$TEST_PUB_KEY1');
    const privateKeyBytes = base64js.toByteArray('$TEST_PRIV_KEY1');
    
    // Create a test move
    const moveData = {
      gameId: 'test-game-123',
      moveNumber: 1,
      fromSquare: 'e2',
      toSquare: 'e4',
      piece: 'p'
    };
    
    // Sign the move data
    const messageBytes = new TextEncoder().encode(JSON.stringify(moveData));
    const signatureBytes = nacl.sign.detached(messageBytes, privateKeyBytes);
    const signatureBase64 = base64js.fromByteArray(signatureBytes);
    
    console.log('⏳ Sending verification request...');
    
    // Send to blockchain API for verification
    const response = await axios.post('http://localhost:5000/api/blockchain/verify', {
      moveData,
      signature: signatureBase64,
      publicKey: '$TEST_PUB_KEY1'
    });
    
    console.log('✅ Verification result:', response.data);
    
    // Also test with modified data (should fail)
    const modifiedData = {...moveData, toSquare: 'e5'};
    const failResponse = await axios.post('http://localhost:5000/api/blockchain/verify', {
      moveData: modifiedData,
      signature: signatureBase64,
      publicKey: '$TEST_PUB_KEY1'
    });
    
    console.log('❌ Modified data verification (should fail):', failResponse.data);
    
    process.exit(0);
  } catch (error) {
    console.error('🚨 Test failed:', error.message);
    if (error.response) {
      console.error('Server response:', error.response.data);
    }
    process.exit(1);
  }
}

// Small delay to ensure backend is ready
setTimeout(testSignature, 2000);
"

# Capture the test result
TEST_RESULT=$?

# Step 5: Clean up
echo "🧹 Cleaning up..."
kill $BACKEND_PID

# Report final status
if [ $TEST_RESULT -eq 0 ]; then
  echo "✅ Signature verification fix test PASSED!"
else
  echo "❌ Signature verification fix test FAILED!"
fi

exit $TEST_RESULT
