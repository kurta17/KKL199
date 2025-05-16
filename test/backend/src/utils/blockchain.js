const { ethers } = require('ethers');
const { MerkleTree } = require('merkletreejs');
const crypto = require('crypto');

/**
 * Verify a signature against a message and a public address
 * @param {string} message - The message that was signed
 * @param {string} signature - The signature to verify
 * @param {string} address - The Ethereum address (public key)
 * @returns {boolean} - Whether the signature is valid
 */
function verifySignature(message, signature, address) {
  try {
    // Recover the signer's address from the signature and message
    const signerAddress = ethers.verifyMessage(message, signature);
    
    // Check if the recovered address matches the expected address
    return signerAddress.toLowerCase() === address.toLowerCase();
  } catch (error) {
    console.error('Error verifying signature:', error);
    return false;
  }
}

/**
 * Create a hash from a move or game state
 * @param {Object} data - The data to hash
 * @returns {string} - The hash as a hex string
 */
function createHash(data) {
  const stringData = JSON.stringify(data);
  return '0x' + crypto
    .createHash('sha256')
    .update(stringData)
    .digest('hex');
}

/**
 * Build a Merkle tree from a series of moves
 * @param {Array} moves - Array of move objects
 * @returns {Object} - The Merkle tree and its root
 */
function buildMerkleTree(moves) {
  // Hash each move
  const leaves = moves.map(move => createHash(move));
  
  // Create Merkle tree
  const tree = new MerkleTree(leaves, crypto.createHash('sha256'), {
    sortPairs: true
  });
  
  const root = tree.getHexRoot();
  
  return {
    tree,
    root,
    leaves
  };
}

/**
 * Generate a proof for a specific move in the Merkle tree
 * @param {Object} tree - The Merkle tree
 * @param {string} leaf - The leaf (hashed move) to generate proof for
 * @returns {Array} - The Merkle proof
 */
function generateProof(tree, leaf) {
  return tree.getHexProof(leaf);
}

/**
 * Verify a proof for a leaf against a root
 * @param {string} root - The Merkle root
 * @param {string} leaf - The leaf (hashed move)
 * @param {Array} proof - The Merkle proof
 * @returns {boolean} - Whether the proof is valid
 */
function verifyProof(root, leaf, proof) {
  return MerkleTree.verify(proof, leaf, root, crypto.createHash('sha256'), {
    sortPairs: true
  });
}

module.exports = {
  verifySignature,
  createHash,
  buildMerkleTree,
  generateProof,
  verifyProof
};
