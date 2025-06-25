#!/bin/bash
# test-signatures.sh
# This script tests Ed25519 signature verification without browser interaction

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== TESTING ED25519 SIGNATURE VERIFICATION ===${NC}"

# Step 1: Check if required packages are installed
echo -e "${YELLOW}Checking required packages...${NC}"
if ! npm list tweetnacl &>/dev/null || ! npm list base64-js &>/dev/null; then
  echo -e "${YELLOW}Installing required packages...${NC}"
  npm install tweetnacl base64-js
fi

# Step 2: Generate test keypairs
echo -e "${YELLOW}Generating test keypairs...${NC}"
if [ ! -f "test_keypairs.txt" ]; then
  chmod +x ./generate-test-keys.sh
  ./generate-test-keys.sh
fi
source test_keypairs.txt

# Step 3: Create a temporary test script
TEST_SCRIPT="/tmp/test_ed25519_$(date +%s).js"

cat > "$TEST_SCRIPT" << EOF
const nacl = require('tweetnacl');
const base64js = require('base64-js');

// Test keys
const privateKeyBase64 = '$TEST_PRIV_KEY1';
const publicKeyBase64 = '$TEST_PUB_KEY1';

// Convert from base64 to Uint8Array
const privateKeyBytes = base64js.toByteArray(privateKeyBase64);
const publicKeyBytes = base64js.toByteArray(publicKeyBase64);

// Test 1: Sign and verify a message
console.log('TEST 1: Basic signature and verification');
const message = 'Hello, ChessChain!';
const messageBytes = new TextEncoder().encode(message);

try {
  // Sign the message
  console.log('Signing message...');
  const signatureBytes = nacl.sign.detached(messageBytes, privateKeyBytes);
  const signatureBase64 = base64js.fromByteArray(signatureBytes);
  console.log('Signature (base64):', signatureBase64.substring(0, 15) + '...');
  
  // Verify the signature
  console.log('Verifying signature...');
  const isValid = nacl.sign.detached.verify(messageBytes, signatureBytes, publicKeyBytes);
  console.log('Signature valid:', isValid);
  
  if (!isValid) {
    process.exit(1);
  }
} catch (error) {
  console.error('Error in Test 1:', error);
  process.exit(1);
}

// Test 2: Try to verify with corrupted message
console.log('\nTEST 2: Corrupted message verification');
const corruptMessage = 'Hello, ChessChain! (corrupted)';
const corruptMessageBytes = new TextEncoder().encode(corruptMessage);

try {
  const signatureBytes = nacl.sign.detached(messageBytes, privateKeyBytes);
  const isValid = nacl.sign.detached.verify(corruptMessageBytes, signatureBytes, publicKeyBytes);
  console.log('Corrupted message verification (should be false):', isValid);
  
  if (isValid) {
    console.error('ERROR: Corrupted message was verified as valid!');
    process.exit(1);
  }
} catch (error) {
  console.error('Error in Test 2:', error);
  process.exit(1);
}

// Test 3: Generate a random keypair and test
console.log('\nTEST 3: Random keypair generation and verification');

try {
  // Generate a new keypair
  const newKeypair = nacl.sign.keyPair();
  const newPrivateKey = newKeypair.secretKey;
  const newPublicKey = newKeypair.publicKey;
  
  // Sign message with new key
  const signature = nacl.sign.detached(messageBytes, newPrivateKey);
  
  // Verify with correct key
  const isValidCorrect = nacl.sign.detached.verify(messageBytes, signature, newPublicKey);
  console.log('Signature with new key valid:', isValidCorrect);
  
  // Try to verify with original key (should fail)
  const isValidWrong = nacl.sign.detached.verify(messageBytes, signature, publicKeyBytes);
  console.log('Cross-verification with wrong key (should be false):', isValidWrong);
  
  if (!isValidCorrect || isValidWrong) {
    console.error('ERROR: Key verification test failed!');
    process.exit(1);
  }
} catch (error) {
  console.error('Error in Test 3:', error);
  process.exit(1);
}

console.log('\n✅ All signature tests passed successfully!');
process.exit(0);
EOF

# Step 4: Run the test script
echo -e "${YELLOW}Running signature verification tests...${NC}"
node "$TEST_SCRIPT"

# Capture the exit code
TEST_RESULT=$?

# Step 5: Report results
if [ $TEST_RESULT -eq 0 ]; then
  echo -e "\n${GREEN}✅ All Ed25519 signature tests PASSED!${NC}"
  echo -e "${GREEN}The ChessChain application should correctly sign and verify chess moves.${NC}"
else
  echo -e "\n${RED}❌ Ed25519 signature tests FAILED!${NC}"
  echo -e "${RED}Please check the cryptography implementation.${NC}"
fi

# Step 6: Clean up
rm "$TEST_SCRIPT"

exit $TEST_RESULT
