import base64
import json
from dataclasses import dataclass
from typing import List

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from ipv8.messaging.payload_dataclass import DataClassPayload


@dataclass
class MoveData(DataClassPayload):
    id: str
    player: str
    move: str
    signature: str  # Base64-encoded signature of the move data f"{id}:{player}:{move}"

    def to_dict(self):
        return {
            "id": self.id,
            "player": self.player,
            "move": self.move,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data["id"],
            player=data["player"],
            move=data["move"],
            signature=data["signature"],
        )


@dataclass
class ChessTransaction(DataClassPayload[1]):
    match_id: str
    moves: List[MoveData]
    winner: str
    player1_pubkey: str  # Base64-encoded public key
    player1_signature: str  # Signature on match outcome
    player2_pubkey: str
    player2_signature: str
    nonce: str
    tx_pubkey: str  # Public key of transaction signer
    signature: str  # Signature on transaction

    def _ensure_moves_are_processed(self):
        """
        Ensures that self.moves contains MoveData objects, attempting conversion
        from strings or dicts if necessary. This method can be called to sanitize
        self.moves before use, regardless of how the instance was created.
        """
        current_moves_attr = getattr(self, 'moves', None)

        if isinstance(current_moves_attr, str):
            try:
                parsed_list = json.loads(current_moves_attr)
                if isinstance(parsed_list, list):
                    current_moves_attr = parsed_list
                else:
                    print(f"Warning: ChessTransaction.moves (nonce: {getattr(self, 'nonce', 'N/A')}) was a JSON string but not a list. Replaced with empty list.")
                    self.moves = []
                    return
            except json.JSONDecodeError:
                print(f"Warning: ChessTransaction.moves (nonce: {getattr(self, 'nonce', 'N/A')}) was a string but not valid JSON. Replaced with empty list.")
                self.moves = []
                return
        
        if not isinstance(current_moves_attr, list):
            # If moves is not a list at this point (e.g., None, or bad initial type), reset to empty.
            # This also handles cases where current_moves_attr might have been an unparsable string.
            if not current_moves_attr == []: # Avoid print if it was already an empty list from failed parsing
                print(f"Warning: ChessTransaction.moves (nonce: {getattr(self, 'nonce', 'N/A')}) is not a list (type: {type(current_moves_attr)}). Replaced with empty list.")
            self.moves = []
            return

        processed_list = []
        for i, item in enumerate(current_moves_attr):
            if isinstance(item, MoveData):
                processed_list.append(item)
            elif isinstance(item, dict):
                try:
                    processed_list.append(MoveData.from_dict(item))
                except Exception as e:
                    print(f"Warning: ChessTransaction (nonce: {getattr(self, 'nonce', 'N/A')}), move item {i} (dict): Could not convert to MoveData: {e}")
            elif isinstance(item, str):
                try:
                    move_dict = json.loads(item)
                    if isinstance(move_dict, dict):
                        processed_list.append(MoveData.from_dict(move_dict))
                    else:
                        print(f"Warning: ChessTransaction (nonce: {getattr(self, 'nonce', 'N/A')}), move item {i} (str): JSON string did not parse to a dict.")
                except json.JSONDecodeError:
                    print(f"Warning: ChessTransaction (nonce: {getattr(self, 'nonce', 'N/A')}), move item {i} (str): String is not valid JSON.")
                except Exception as e:
                    print(f"Warning: ChessTransaction (nonce: {getattr(self, 'nonce', 'N/A')}), move item {i} (str to dict): Could not convert to MoveData: {e}")
            else:
                print(f"Warning: ChessTransaction (nonce: {getattr(self, 'nonce', 'N/A')}), move item {i}: Unexpected type {type(item)}, skipped.")
        
        self.moves = processed_list

    def __post_init__(self):
        self._ensure_moves_are_processed()

    def _serialize_moves_for_signing(self) -> str:
        self._ensure_moves_are_processed() # Ensure moves are MoveData objects
        """Serialize moves to a JSON string for signing, consistent with the original format."""
        return json.dumps([move.to_dict() for move in self.moves])

    def to_dict(self):
        self._ensure_moves_are_processed() # Ensure moves are MoveData objects
        """Convert the transaction to a dictionary."""
        return {
            "match_id": self.match_id,
            "moves": [move.to_dict() for move in self.moves],
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
            moves=[MoveData.from_dict(move_data) for move_data in data["moves"]],
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
        self._ensure_moves_are_processed() # Ensure moves are MoveData objects before verification
        """Verify all signatures in the transaction."""
        try:
            # Decode public keys
            p1_pk_bytes = base64.b64decode(self.player1_pubkey)
            p2_pk_bytes = base64.b64decode(self.player2_pubkey)
            tx_pk_bytes = base64.b64decode(self.tx_pubkey)
            p1_pk = Ed25519PublicKey.from_public_bytes(p1_pk_bytes)
            p2_pk = Ed25519PublicKey.from_public_bytes(p2_pk_bytes)
            tx_pk = Ed25519PublicKey.from_public_bytes(tx_pk_bytes)

            if not self.moves:
                print(f"Invalid transaction {getattr(self, 'nonce', 'N/A')}: Empty move list")
                return False

            # Verify move signatures and alternation
            for i, move_obj in enumerate(self.moves):
                # Defensive check, though _ensure_moves_are_processed should guarantee MoveData
                if not isinstance(move_obj, MoveData):
                    print(f"Critical Error: Transaction {getattr(self, 'nonce', 'N/A')}, move item {i} is type {type(move_obj)}, not MoveData, during verification.")
                    return False
                player = move_obj.player
                move_str = move_obj.move
                sig = base64.b64decode(move_obj.signature)
                move_data_to_verify = f"{move_obj.id}:{player}:{move_str}".encode()
                pk = p1_pk if player == "player1" else p2_pk
                try:
                    pk.verify(sig, move_data_to_verify)
                except InvalidSignature:
                    print(f"Invalid move signature for move {move_obj.id}")
                    return False
                # Check alternation
                expected_player = "player1" if i % 2 == 0 else "player2"
                if player != expected_player:
                    print(f"Invalid move order at move {move_obj.id}")
                    return False

            # Verify winner is the last move's player
            last_move = self.moves[-1]
            if last_move.player != self.winner:
                print(f"Invalid winner: {self.winner} does not match last move by {last_move.player}")
                return False

            # Verify player signatures on match outcome
            serialized_moves_for_signing = self._serialize_moves_for_signing()
            outcome = f"{self.match_id}:{self.winner}:{serialized_moves_for_signing}".encode()
            try:
                p1_pk.verify(base64.b64decode(self.player1_signature), outcome)
                p2_pk.verify(base64.b64decode(self.player2_signature), outcome)
            except InvalidSignature:
                print(f"Invalid player signature for match {self.match_id}")
                return False

            # Verify transaction signature
            tx_data = f"{self.match_id}:{serialized_moves_for_signing}:{self.winner}:{self.nonce}".encode()
            try:
                tx_pk.verify(base64.b64decode(self.signature), tx_data)
            except InvalidSignature:
                print(f"Invalid transaction signature for {self.nonce}")
                return False

            return True
        except Exception as e:
            print(f"Error verifying transaction {self.nonce}: {e}")
            return False