from ipv8.lazy_community import lazy_wrapper
from ipv8.types import Peer # Added
from ipv8.messaging.serialization import default_serializer # Added for unpacking

# Assuming models are in a directory 'models' at the same level as 'community' parent
# Adjust the import path if your project structure is different.
from models.models import ChessTransaction, ProposedBlockPayload, ProposerAnnouncement, MoveData
from cryptography.exceptions import InvalidSignature # Added
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey # Added
from utils.merkle import MerkleTree # Added for Merkle root verification


@lazy_wrapper(MoveData)
def on_move(self, peer: Peer, payload: MoveData) -> None:
    """Handle incoming move messages."""
    packed_move = default_serializer.pack_serializable(payload)
    key = f"{payload.match_id}:{payload.id}".encode()
    
    try:
        with self.db_env.begin(write=True) as txn:
            moves_db = self.db_env.open_db(b'moves', txn=txn, create=True)
            if txn.get(key, db=moves_db):
                self.logger.info(f"Move {payload.id} for match {payload.match_id} already exists. Skipping.")
                return
            txn.put(key, packed_move, db=moves_db)
        self.logger.info(f"Stored move {payload.id} for match {payload.match_id} from {peer.mid.hex()[:8] if peer else 'Unknown Peer'}")
    except Exception as e:
        self.logger.error(f"Error storing move {payload.id} for match {payload.match_id}: {e}")


@lazy_wrapper(ChessTransaction)
def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
    """Handle incoming transactions with verification and storage using default_serializer."""
    try:
        proposer_pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.proposer_pubkey_hex))
        tx_data_to_verify = f"{payload.match_id}:{payload.winner}:{payload.nonce}:{payload.proposer_pubkey_hex}".encode()
        proposer_pubkey.verify(bytes.fromhex(payload.signature), tx_data_to_verify)
        self.logger.info(f"Transaction {payload.nonce} signature verified successfully.")
    except InvalidSignature:
        self.logger.warning(f"Transaction {payload.nonce} from {peer.mid.hex()[:8] if peer else 'Unknown Peer'} failed signature verification. Discarding.")
        return
    except Exception as e:
        self.logger.error(f"Error during signature verification for transaction {payload.nonce}: {e}. Discarding.")
        return

    if payload.nonce in self.mempool or self.is_transaction_in_db(payload.nonce):
        self.logger.info(f"Transaction {payload.nonce} already processed or in mempool. Skipping.")
        return

    self.mempool[payload.nonce] = payload 
    self.logger.info(f"Transaction {payload.nonce} added to mempool. Mempool size: {len(self.mempool)}")

    try:
        packed_tx = default_serializer.pack_serializable(payload)
        with self.db_env.begin(write=True) as txn:
            tx_db = self.db_env.open_db(b'transactions', txn=txn, create=True)
            txn.put(payload.nonce.encode('utf-8'), packed_tx, db=tx_db)
        self.logger.info(f"Accepted and stored transaction {payload.nonce} from {peer.mid.hex()[:8] if peer else 'Unknown Peer'}")
    except Exception as e:
        self.logger.error(f"Failed to store transaction {payload.nonce} in DB: {e}")
        if payload.nonce in self.mempool:
            del self.mempool[payload.nonce]


@lazy_wrapper(ProposerAnnouncement)
async def on_proposer_announcement(self, peer: Peer, payload: ProposerAnnouncement) -> None:
    """Handles incoming proposer announcements."""
    print(f"Received ProposerAnnouncement for round {payload.round_seed_hex[:8]} from {payload.proposer_pubkey_hex[:8]} (peer {peer.mid.hex()[:8] if peer else 'Unknown Peer'})")


async def on_proposed_block(self, source_address, data):
    # Unpack the data manually
    peer = Peer(source_address)
    payload, _ = default_serializer.unpack_serializable(ProposedBlockPayload, data)
    """Handles an incoming proposed block with full validation."""
    self.logger.info(f"Received ProposedBlockPayload for round {payload.round_seed_hex[:8]} from peer {peer.mid.hex()[:8] if peer else 'Unknown Peer'} (claimed proposer: {payload.proposer_pubkey_hex[:8]})")

    try:
        proposer_public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.proposer_pubkey_hex))
        
        # Update signature verification to include timestamp and previous block hash
        block_data_to_verify_str = f"{payload.round_seed_hex}:{payload.merkle_root}:{payload.proposer_pubkey_hex}:{payload.previous_block_hash}:{payload.timestamp}"
        block_data_to_verify_bytes = block_data_to_verify_str.encode('utf-8')
        block_signature_bytes = bytes.fromhex(payload.signature)
        
        proposer_public_key.verify(block_signature_bytes, block_data_to_verify_bytes)
        self.logger.info(f"Block signature VERIFIED for block by {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]}.")
            
        # Verify previous block hash is valid
        latest_block_hash = self.get_latest_block_hash()
        if payload.previous_block_hash != latest_block_hash:
            self.logger.warning(f"Previous block hash mismatch. Expected {latest_block_hash}, got {payload.previous_block_hash}. Discarding.")
            return
        
    except InvalidSignature:
        self.logger.warning(f"Block signature INVALID for block by {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]}. Discarding block.")
        return
    except Exception as e:
        self.logger.error(f"Error during block signature verification for block by {payload.proposer_pubkey_hex[:8]}: {e}. Discarding block.")
        return

    if not payload.transaction_hashes:
        if payload.merkle_root != MerkleTree([]).get_root():
            self.logger.warning(f"Block from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} has no transaction hashes, but Merkle root {payload.merkle_root} does not match expected empty root. Discarding.")
            return
        self.logger.info(f"Block from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} is an empty block and Merkle root is consistent.")
    else:
        try:
            reconstructed_merkle_tree = MerkleTree(payload.transaction_hashes)
            reconstructed_merkle_root = reconstructed_merkle_tree.get_root()
            if reconstructed_merkle_root == payload.merkle_root:
                self.logger.info(f"Merkle root VERIFIED for block by {payload.proposer_pubkey_hex[:8]} (found {len(payload.transaction_hashes)} tx_hashes). Root: {payload.merkle_root}")
            else:
                self.logger.warning(f"Merkle root INVALID for block by {payload.proposer_pubkey_hex[:8]}. Expected {payload.merkle_root}, got {reconstructed_merkle_root}. Discarding block.")
                return
        except Exception as e:
            self.logger.error(f"Error during Merkle root verification for block by {payload.proposer_pubkey_hex[:8]}: {e}. Discarding block.")
            return
            
    self.logger.info(f"Block from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} PASSED all verifications.")
    
    # If the block passes all verification checks, create and send a vote
    # Only vote if we meet the stake requirement
    if self.stakes[self.pubkey_bytes] >= self.MIN_STAKE:
        await self.send_validator_vote(payload)
    else:
        self.logger.info(f"Not voting on block from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} due to insufficient stake.")
