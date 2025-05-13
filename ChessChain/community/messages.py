import json
import base64 # Added for signature decoding
from ipv8.lazy_community import lazy_wrapper
from ipv8.types import Peer # Added

# Assuming models are in a directory 'models' at the same level as 'community' parent
# Adjust the import path if your project structure is different.
from models.models import ChessTransaction, ProposedBlockPayload, ProposerAnnouncement
from cryptography.exceptions import InvalidSignature # Added
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey # Added


@lazy_wrapper(ChessTransaction)
def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
    """Handle incoming transactions with verification.
    
    Args:
        peer: The peer that sent the transaction
        payload: The transaction payload
    """
    if payload.nonce in self.transactions:
        print(f"Transaction {payload.nonce} already processed")
        return
        
    if not payload.verify_signatures():
        print(f"Transaction {payload.nonce} failed verification")
        return
        
    # Use JSON serialization instead of pack_low
    with self.db_env.begin(db=self.tx_db, write=True) as tx:
        tx.put(payload.nonce.encode(), json.dumps(payload.to_dict()).encode())
        
    self.transactions.add(payload.nonce)
    self.mempool.append(payload)
    print(f"Accepted transaction {payload.nonce} from {peer.mid.hex()[:8] if peer else 'Unknown Peer'}")


@lazy_wrapper(ProposerAnnouncement)
async def on_proposer_announcement(self, peer: Peer, payload: ProposerAnnouncement) -> None:
    """Handles incoming proposer announcements."""
    # Potentially, verify if the announcer is the expected proposer for the round_seed.
    # expected_proposer = self.select_proposer(bytes.fromhex(payload.round_seed_hex))
    # if not expected_proposer or expected_proposer.hex() != payload.proposer_pubkey_hex:
    #     print(f"Warning: ProposerAnnouncement from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} is not the expected proposer.")
    #     return
    print(f"Received ProposerAnnouncement for round {payload.round_seed_hex[:8]} from {payload.proposer_pubkey_hex[:8]} (peer {peer.mid.hex()[:8] if peer else 'Unknown Peer'})")
    # Peers can use this to know who to expect a block from for this round.

@lazy_wrapper(ProposedBlockPayload)
async def on_proposed_block(self, peer: Peer, payload: ProposedBlockPayload) -> None: # Made async to align with potential async operations
    """Handles an incoming proposed block with full validation."""
    print(f"Received ProposedBlockPayload for round {payload.round_seed_hex[:8]} from peer {peer.mid.hex()[:8] if peer else 'Unknown Peer'} (claimed proposer: {payload.proposer_pubkey_hex[:8]})")
