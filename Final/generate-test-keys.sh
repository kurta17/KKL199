#!/bin/bash
# Generate test keypairs for ChessChain using Node.js

# Output file for key pairs
OUTPUT_FILE="test_keypairs.txt"

# JavaScript code to generate Ed25519 keypairs
NODE_SCRIPT=$(cat << 'EOF'
const nacl = require('tweetnacl');
const base64js = require('base64-js');

// Generate a new Ed25519 keypair
function generateKeypair() {
  const keyPair = nacl.sign.keyPair();
  
  // Convert the keys to base64 for storage
  const privateKeyBase64 = base64js.fromByteArray(keyPair.secretKey);
  const publicKeyBase64 = base64js.fromByteArray(keyPair.publicKey);
  
  return {
    privateKeyBase64,
    publicKeyBase64
  };
}

// Generate key pairs for testing
const user1 = generateKeypair();
const user2 = generateKeypair();

console.log(`
# Test keypairs for ChessChain
# Generated on ${new Date().toISOString()}

# User 1
export TEST_PRIV_KEY1="${user1.privateKeyBase64}"
export TEST_PUB_KEY1="${user1.publicKeyBase64}"

# User 2
export TEST_PRIV_KEY2="${user2.privateKeyBase64}"
export TEST_PUB_KEY2="${user2.publicKeyBase64}"
`);
EOF
)

# Check if necessary packages are installed
if ! npm list -g tweetnacl &> /dev/null || ! npm list -g base64-js &> /dev/null; then
  echo "Installing required packages..."
  npm install -g tweetnacl base64-js
fi

# Generate keypairs using Node.js
echo "Generating Ed25519 keypairs for testing..."
node -e "$NODE_SCRIPT" > "$OUTPUT_FILE"

echo "Generated keypairs and saved to $OUTPUT_FILE"
echo "To use these keys, run: source $OUTPUT_FILE"

# Print public keys for easy access
grep "TEST_PUB" "$OUTPUT_FILE"
