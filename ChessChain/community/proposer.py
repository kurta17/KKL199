import hashlib
import time
from typing import List, TYPE_CHECKING
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from ipv8.messaging.serialization import default_serializer

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from . import ChessCommunity
else:
    from . import ChessCommunity

from utils.utils import lottery_selection
from models.models import ProposedBlockPayload, ProposerAnnouncement
from ipv8.types import Peer
from utils.merkle import MerkleTree

class Proposer:
    def __init__(self, community: 'ChessCommunity'):
        self.community = community
        self.logger = community.logger
        self.stakes = community.stakes
        self.pubkey_bytes = community.pubkey_bytes
        self.db_env = community.db_env

    def checking_proposer(self, seed: bytes) -> bool:
        peer_ids = []
        for peer in self.community.get_peers():
            if peer.mid != self.pubkey_bytes:
                peer_ids.append(peer.mid.hex())
        peer_ids.append(self.pubkey_bytes.hex())
        is_proposer = lottery_selection(
            seed=seed,
            p_id=self.pubkey_bytes,
            total_stake=self.community.stake.total_stake(),
            peers=peer_ids
        )
        if is_proposer:
            self.logger.info(f"I am the proposer for round with seed {seed.hex()[:8]}")
        else:
            self.logger.info(f"I am NOT the proposer for round with seed {seed.hex()[:8]}")
        return is_proposer

    async def on_proposer_announcement(self, peer: Peer, payload: ProposerAnnouncement) -> None:
        print(f"Received ProposerAnnouncement for round {payload.round_seed_hex[:8]} from {payload.proposer_pubkey_hex[:8]} (peer {peer.mid.hex()[:8] if peer else 'Unknown Peer'})")

    async def on_proposed_block(self, peer: Peer, payload: ProposedBlockPayload) -> None:
        if payload.previous_block_hash != self.community.blockchain.get_latest_block_hash():
            fork_resolved = await self.community.sync.resolve_fork_with_retry(payload)
            if not fork_resolved:
                self.logger.warning(f"Previous block hash mismatch. Expected {self.community.blockchain.get_latest_block_hash()[:16]}, got {payload.previous_block_hash[:16]}. Attempting to sync blocks...")
                return
            else:
                self.logger.info(f"Fork successfully resolved!")
        self.logger.info(f"Received ProposedBlockPayload for round {payload.round_seed_hex[:8]} from peer {peer.mid.hex()[:8] if peer else 'Unknown Peer'} (claimed proposer: {payload.proposer_pubkey_hex[:8]})")
        try:
            proposer_public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.proposer_pubkey_hex))
            block_data_to_verify_str = f"{payload.round_seed_hex}:{payload.merkle_root}:{payload.proposer_pubkey_hex}:{payload.previous_block_hash}:{payload.timestamp}"
            block_data_to_verify_bytes = block_data_to_verify_str.encode('utf-8')
            block_signature_bytes = bytes.fromhex(payload.signature)
            proposer_public_key.verify(block_signature_bytes, block_data_to_verify_bytes)
            self.logger.info(f"Block signature VERIFIED for block by {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]}.")
            latest_block_hash = self.community.blockchain.get_latest_block_hash()
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
        if self.stakes[self.community.pubkey_bytes] >= self.community.MIN_STAKE:
            await self.community.consensus.send_validator_vote(payload)
        else:
            self.logger.info(f"Not voting on block from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} due to insufficient stake.")

    def store_proposed_block(self, block: ProposedBlockPayload) -> None:
        proposed_blocks_db = self.db_env.open_db(b'proposed_blocks', create=True)
        block_id = f"{block.round_seed_hex}:{block.proposer_pubkey_hex[:8]}".encode('utf-8')
        serialized_block = default_serializer.pack_serializable(block)
        with self.db_env.begin(db=proposed_blocks_db, write=True) as txn:
            txn.put(block_id, serialized_block)
        self.logger.info(f"Stored proposed block with ID {block_id.decode('utf-8')}")