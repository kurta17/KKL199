import base64
import json
from dataclasses import dataclass
from typing import List
 
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from ipv8.messaging.payload_dataclass import DataClassPayload
 
CHESS_TRANSACTION_MSG_ID = 1
PROPOSED_BLOCK_MSG_ID = 2
PROPOSER_ANNOUNCEMENT_MSG_ID = 3
MOVE_DATA_MSG_ID = 4
 
@dataclass
class ProposedBlockPayload(DataClassPayload[PROPOSED_BLOCK_MSG_ID]):
    """Payload for broadcasting a proposed block."""
    round_seed_hex: str
    transactions_json: str
    proposer_pubkey_hex: str
    signature: str
 
@dataclass
class ProposerAnnouncement(DataClassPayload[PROPOSER_ANNOUNCEMENT_MSG_ID]):
    """Payload for a peer announcing it is the proposer for a round."""
    round_seed_hex: str
    proposer_pubkey_hex: str
 
@dataclass
class MoveData(DataClassPayload[MOVE_DATA_MSG_ID]):
    id: int  # Changed to int
    player: str
    move: str
    signature: str  # Base64-encoded signature of the move data f"{id}:{player}:{move}"
 
    def __post_init__(self):
        # Ensure id is int
        if not isinstance(self.id, int):
            original_id_repr = repr(getattr(self, 'id', 'MISSING'))
            try:
                self.id = int(self.id)
            except (ValueError, TypeError) as e:
                raise ValueError(f"MoveData.id ({original_id_repr}) must be an integer or a string convertible to an integer.") from e
       
        # Ensure other fields are strings
        if not isinstance(self.player, str):
            self.player = str(self.player)
        if not isinstance(self.move, str):
            self.move = str(self.move)
        if not isinstance(self.signature, str):
            self.signature = str(self.signature)
 
    def to_dict(self):
        return {
            "id": self.id,
            "player": self.player,
            "move": self.move,
            "signature": self.signature,
        }
 
    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise TypeError(f"MoveData.from_dict expects a dict, got {type(data)}")
 
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
 
        signature = data.get("signature")
        if signature is None:
            raise ValueError("MoveData.from_dict: 'signature' field is missing.")
       
        return cls(
            id=move_id,
            player=str(player),
            move=str(move_val),
            signature=str(signature),
        )
 
@dataclass
class ChessTransaction(DataClassPayload[CHESS_TRANSACTION_MSG_ID]):
    match_id: str
    winner: str
    player1_pubkey: str  # Base64-encoded public key
    player1_signature: str  # Signature on match outcome
    player2_pubkey: str
    player2_signature: str
    nonce: str
    tx_pubkey: str  # Public key of transaction signer
    signature: str  # Signature on transaction
 
    def to_dict(self):
        """Convert the transaction to a dictionary."""
        return {
            "match_id": self.match_id,
            "winner": self.winner,
            "player1_pubkey": self.player1_pubkey,
            "player1_signature": self.player1_signature,
            "player2_pubkey": self.player2_pubkey,
            "player2_signature": self.player2_signature,
            "nonce": self.nonce,
            "tx_pubkey": self.tx_pubkey,
            "signature": self.signature,
        }
 
    @classmethod
    def from_dict(cls, data):
        """Create a transaction from a dictionary."""
        return cls(
            match_id=data["match_id"],
            winner=data["winner"],
            player1_pubkey=data["player1_pubkey"],
            player1_signature=data["player1_signature"],
            player2_pubkey=data["player2_pubkey"],
            player2_signature=data["player2_signature"],
            nonce=data["nonce"],
            tx_pubkey=data["tx_pubkey"],
            signature=data["signature"],
        )
 
    def verify_signatures(self) -> bool:
        """Verify all signatures in the transaction."""
        try:
            # Decode public keys
            p1_pk_bytes = base64.b64decode(self.player1_pubkey)
            p2_pk_bytes = base64.b64decode(self.player2_pubkey)
            tx_pk_bytes = base64.b64decode(self.tx_pubkey)
            p1_pk = Ed25519PublicKey.from_public_bytes(p1_pk_bytes)
            p2_pk = Ed25519PublicKey.from_public_bytes(p2_pk_bytes)
            tx_pk = Ed25519PublicKey.from_public_bytes(tx_pk_bytes)
 
            # Verify player signatures on match outcome
            outcome = f"{self.match_id}:{self.winner}".encode()
            try:
                p1_pk.verify(base64.b64decode(self.player1_signature), outcome)
                p2_pk.verify(base64.b64decode(self.player2_signature), outcome)
            except InvalidSignature:
                print(f"Invalid player signature for match {self.match_id}")
                return False
 
            # Verify transaction signature
            tx_data = f"{self.match_id}:{self.winner}:{self.nonce}".encode()
            try:
                tx_pk.verify(base64.b64decode(self.signature), tx_data)
            except InvalidSignature:
                print(f"Invalid transaction signature for {self.nonce}")
                return False
 
            return True
        except Exception as e:
            print(f"Error verifying transaction {self.nonce}: {e}")
            return False