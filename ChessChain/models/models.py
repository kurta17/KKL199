import base64
import json
from dataclasses import dataclass, field
from typing import List

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

from ipv8.messaging.payload_dataclass import DataClassPayload, Serializable

CHESS_TRANSACTION_MSG_ID = 1
PROPOSED_BLOCK_MSG_ID = 2
PROPOSER_ANNOUNCEMENT_MSG_ID = 3
MOVE_DATA_MSG_ID = 4
VALIDATOR_VOTE_MSG_ID = 5
BLOCK_CONFIRMATION_MSG_ID = 6


class BlockSyncRequest(Serializable):
    msg_id = 8
    """Request blocks from a given hash."""
    format_list = ['varlenH', 'I']

    
    def __init__(self, block_hash: str, count: int = 10):
        self.block_hash = block_hash
        self.count = count
    
    @classmethod
    def from_unpack_list(cls, block_hash: str, count: int):
        return BlockSyncRequest(block_hash, count)

class BlockSyncResponse(Serializable):
    """Response to a block sync request containing serialized blocks."""
    msg_id = 7

    format_list = ['varlenH', 'varlenH'] 
    
    def __init__(self, request_hash: str, blocks_data: str):
        self.request_hash = request_hash
        self.blocks_data = blocks_data
        
    @classmethod
    def from_unpack_list(cls, request_hash: str, blocks_data: str):
        return BlockSyncResponse(request_hash, blocks_data)


@dataclass
class ProposedBlockPayload(DataClassPayload):
    """Payload for broadcasting a proposed block."""
    msg_id = PROPOSED_BLOCK_MSG_ID

    round_seed_hex: str
    transaction_hashes_str: str  # Changed from transaction_hashes: List[str]
    merkle_root: str
    proposer_pubkey_hex: str
    signature: str
    previous_block_hash: str
    timestamp: int = 0

    # Keep only ONE property method
    @property
    def transaction_hashes(self) -> List[str]:
        """Get transaction hashes as a list."""
        if not self.transaction_hashes_str:
            return []
        return self.transaction_hashes_str.split(",")
    
    # Remove the duplicate property with the same name
    
    @classmethod
    def create(cls, round_seed_hex: str, transaction_hashes: List[str], 
               merkle_root: str, proposer_pubkey_hex: str,
               signature: str, previous_block_hash: str, timestamp: int = 0):
        """Factory method to create from a list of transaction hashes."""
        transaction_hashes_str = ",".join(transaction_hashes)
        return cls(
            round_seed_hex=round_seed_hex,
            transaction_hashes_str=transaction_hashes_str,  # This is correct
            merkle_root=merkle_root,
            proposer_pubkey_hex=proposer_pubkey_hex,
            signature=signature,
            previous_block_hash=previous_block_hash,
            timestamp=timestamp
        )

@dataclass
class ProposerAnnouncement(DataClassPayload):
    """Payload for a peer announcing it is the proposer for a round."""
    msg_id = PROPOSER_ANNOUNCEMENT_MSG_ID  # Assign msg_id directly

    round_seed_hex: str
    proposer_pubkey_hex: str

@dataclass
class MoveData(DataClassPayload):
    msg_id = MOVE_DATA_MSG_ID  # Assign msg_id directly

    match_id: str  # Added
    id: int
    player: str
    move: str
    timestamp: float  # Added
    signature: str  # Base64-encoded signature of the move data f"{match_id}:{id}:{player}:{move}:{timestamp}"

    def __post_init__(self):
        # Ensure id is int
        if not isinstance(self.id, int):
            original_id_repr = repr(getattr(self, 'id', 'MISSING'))
            try:
                self.id = int(self.id)
            except (ValueError, TypeError) as e:
                raise ValueError(f"MoveData.id ({original_id_repr}) must be an integer or a string convertible to an integer.") from e
        
        # Ensure other fields are strings where appropriate
        if not isinstance(self.match_id, str):
            self.match_id = str(self.match_id)
        if not isinstance(self.player, str):
            self.player = str(self.player)
        if not isinstance(self.move, str):
            self.move = str(self.move)
        if not isinstance(self.timestamp, float):
            try:
                self.timestamp = float(self.timestamp)
            except (ValueError, TypeError) as e:
                original_ts_repr = repr(getattr(self, 'timestamp', 'MISSING'))
                raise ValueError(f"MoveData.timestamp ({original_ts_repr}) must be a float or convertible to a float.") from e
        if not isinstance(self.signature, str):
            self.signature = str(self.signature)

    def to_dict(self):
        return {
            "match_id": self.match_id, # Added
            "id": self.id,
            "player": self.player,
            "move": self.move,
            "timestamp": self.timestamp, # Added
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise TypeError(f"MoveData.from_dict expects a dict, got {type(data)}")

        try:
            match_id = data["match_id"]
        except KeyError:
            raise ValueError("MoveData.from_dict: 'match_id' field is missing from input data.")

        try:
            move_id_val = data["id"]
        except KeyError:
            raise ValueError("MoveData.from_dict: 'id' field is missing from input data.")
        
        try:
            move_id = int(move_id_val)
        except (ValueError, TypeError) as e:
            raise ValueError(f"MoveData.from_dict: 'id' field ('{move_id_val}') must be an integer or a string convertible to an integer.") from e

        player = data.get("player")
        if player is None:
            raise ValueError("MoveData.from_dict: 'player' field is missing.")
        
        move_val = data.get("move")
        if move_val is None:
            raise ValueError("MoveData.from_dict: 'move' field is missing.")

        try:
            timestamp_val = data["timestamp"]
        except KeyError:
            raise ValueError("MoveData.from_dict: 'timestamp' field is missing from input data.")
        
        try:
            timestamp = float(timestamp_val)
        except (ValueError, TypeError) as e:
            raise ValueError(f"MoveData.from_dict: 'timestamp' field ('{timestamp_val}') must be a float or convertible to a float.") from e

        signature = data.get("signature")
        if signature is None:
            raise ValueError("MoveData.from_dict: 'signature' field is missing.")
        
        return cls(
            match_id=str(match_id),
            id=move_id,
            player=str(player),
            move=str(move_val),
            timestamp=timestamp,
            signature=str(signature),
        )

@dataclass
class ChessTransaction(DataClassPayload):
    msg_id = CHESS_TRANSACTION_MSG_ID  # Assign msg_id directly

    match_id: str
    winner: str
    moves_hash: str  # Added to store a hash of concatenated move IDs or a Merkle root of moves
    nonce: str
    proposer_pubkey_hex: str  # Added to align with send_moves and general block proposal logic
    signature: str  # Signature on transaction (e.g., match_id:winner:nonce:proposer_pubkey_hex)

    def to_dict(self):
        """Convert the transaction to a dictionary."""
        return {
            "match_id": self.match_id,
            "winner": self.winner,
            "moves_hash": self.moves_hash,  # Added
            "nonce": self.nonce,
            "proposer_pubkey_hex": self.proposer_pubkey_hex,  # Added
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data):
        """Create a transaction from a dictionary."""
        return cls(
            match_id=data["match_id"],
            winner=data["winner"],
            moves_hash=data["moves_hash"],  # Added
            nonce=data["nonce"],
            proposer_pubkey_hex=data["proposer_pubkey_hex"],  # Added
            signature=data["signature"],
        )

    def verify_signatures(self) -> bool:
        """Verify the signature of the transaction proposer."""
        try:
            proposer_pk_bytes = bytes.fromhex(self.proposer_pubkey_hex)
            proposer_pk = Ed25519PublicKey.from_public_bytes(proposer_pk_bytes)

            # Verify transaction signature
            # The signed data should match what's signed in ChessCommunity.send_moves
            tx_data = f"{self.match_id}:{self.winner}:{self.nonce}:{self.proposer_pubkey_hex}".encode()
            proposer_pk.verify(bytes.fromhex(self.signature), tx_data)
            return True
        except InvalidSignature:
            print(f"Invalid transaction signature for nonce {self.nonce} by proposer {self.proposer_pubkey_hex}")
            return False
        except Exception as e:
            print(f"Error verifying transaction {self.nonce}: {e}")
            return False

@dataclass
class ValidatorVote(DataClassPayload):
    """Payload for validators voting on proposed blocks."""
    msg_id = VALIDATOR_VOTE_MSG_ID

    round_seed_hex: str  # Round this vote is for
    block_merkle_root: str  # Merkle root of the voted block
    proposer_pubkey_hex: str  # Proposer of the block being voted on
    validator_pubkey_hex: str  # Validator's public key
    vote: bool  # True for approval, False for rejection
    signature: str  # Validator signature on vote data

@dataclass
class BlockConfirmation(DataClassPayload):
    """Payload for block finalization confirmation once quorum is reached."""
    msg_id = BLOCK_CONFIRMATION_MSG_ID

    round_seed_hex: str  # Round this confirmation is for
    block_merkle_root: str  # Merkle root of the confirmed block
    proposer_pubkey_hex: str  # Proposer of the confirmed block
    timestamp: int  # Block timestamp
    signatures_count: int  # Number of validator signatures (quorum count)
    confirmer_pubkey_hex: str  # Public key of peer who confirmed quorum
    signature: str  # Confirmer's signature