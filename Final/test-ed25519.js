// Test script for Ed25519 key generation and signing
const nacl = require('tweetnacl');
const base64js = require('base64-js');

console.log('Starting Ed25519 test script...');

// Function to convert string to Uint8Array
function strToUint8Array(str) {
  return new TextEncoder().encode(str);
}

// Generate a new Ed25519 keypair
function generateKeypair() {
  const keyPair = nacl.sign.keyPair();
  
  // Convert the keys to base64 for storage/display
  const privateKeyBase64 = base64js.fromByteArray(keyPair.secretKey);
  const publicKeyBase64 = base64js.fromByteArray(keyPair.publicKey);
  
  return {
    privateKeyBase64,
    publicKeyBase64,
    keyPair
  };
}

// Sign a message using Ed25519
function signMessage(message, privateKey) {
  const messageBytes = strToUint8Array(message);
  
  // Sign the message
  const signatureBytes = nacl.sign.detached(
    messageBytes,
    privateKey
  );
  
  // Convert signature to base64
  return base64js.fromByteArray(signatureBytes);
}

// Verify a signature
function verifySignature(message, signature, publicKey) {
  const messageBytes = strToUint8Array(message);
  
  return nacl.sign.detached.verify(
    messageBytes,
    signature,
    publicKey
  );
}

// Generate a keypair
console.log('Generating Ed25519 keypair...');
const { privateKeyBase64, publicKeyBase64, keyPair } = generateKeypair();
console.log('Private key (base64):', privateKeyBase64.substring(0, 15) + '...');
console.log('Public key (base64):', publicKeyBase64);

// Test data for a chess move
const moveData = {
  gameId: 'game123',
  moveNumber: 1,
  fromSquare: 'e2',
  toSquare: 'e4',
  piece: 'p',
  promotion: null,
  playerColor: 'white',
  timestamp: Date.now()
};

const moveDataString = JSON.stringify(moveData);
console.log('\nMessage to sign:', moveDataString);

// Sign the message
const signature = signMessage(moveDataString, keyPair.secretKey);
console.log('Signature (base64):', signature.substring(0, 15) + '...');

// Verify the signature
const isValid = verifySignature(
  moveDataString, 
  base64js.toByteArray(signature),
  keyPair.publicKey
);
console.log('Signature valid:', isValid);

// Test with modified message (should fail)
const modifiedMoveData = { ...moveData, toSquare: 'e5' };
const modifiedMoveDataString = JSON.stringify(modifiedMoveData);
const isValidModified = verifySignature(
  modifiedMoveDataString,
  base64js.toByteArray(signature),
  keyPair.publicKey
);
console.log('Modified message signature valid (should be false):', isValidModified);

// Print values in format needed for test script
console.log('\nFor test-blockchain-game.sh:');
console.log(`TEST_PUB_KEY1="${publicKeyBase64}"`);
