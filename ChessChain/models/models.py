import base64
import json
from dataclasses import dataclass
from typing import List

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from ipv8.messaging.payload_dataclass import DataClassPayload


@dataclass
class ChessTransaction(DataClassPayload[1]):
    match_id: str
    moves: str  # JSON string of moves
    winner: str
    player1_pubkey: str  # Base64-encoded public key
    player1_signature: str  # Signature on match outcome
    player2_pubkey: str
    player2_signature: str
    nonce: str
    tx_pubkey: str  # Public key of transaction signer
    signature: str  # Signature on transaction

    def to_dict(self):
        """Convert the transaction to a dictionary, parsing the JSON moves."""
        return {
            "match_id": self.match_id,
            "moves": json.loads(self.moves),
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
        """Create a transaction from a dictionary, serializing moves to a JSON string."""
        return cls(
            match_id=data["match_id"],
            moves=json.dumps(data["moves"]) if isinstance(data["moves"], list) else data["moves"],
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

            # Parse moves
            moves = json.loads(self.moves)
            if not moves:
                print(f"Invalid transaction {self.nonce}: Empty move list")
                return False

            # Verify move signatures and alternation
            for i, move in enumerate(moves):
                player = move["player"]
                move_str = move["move"]
                sig = base64.b64decode(move["signature"])
                move_data = f"{move['id']}:{player}:{move_str}".encode()
                pk = p1_pk if player == "player1" else p2_pk
                try:
                    pk.verify(sig, move_data)
                except InvalidSignature:
                    print(f"Invalid move signature for move {move['id']}")
                    return False
                # Check alternation
                expected_player = "player1" if i % 2 == 0 else "player2"
                if player != expected_player:
                    print(f"Invalid move order at move {move['id']}")
                    return False

            # Verify winner is the last move's player
            last_move = moves[-1]
            if last_move["player"] != self.winner:
                print(f"Invalid winner: {self.winner} does not match last move by {last_move['player']}")
                return False

            # Verify player signatures on match outcome
            outcome = f"{self.match_id}:{self.winner}:{self.moves}".encode()
            try:
                p1_pk.verify(base64.b64decode(self.player1_signature), outcome)
                p2_pk.verify(base64.b64decode(self.player2_signature), outcome)
            except InvalidSignature:
                print(f"Invalid player signature for match {self.match_id}")
                return False

            # Verify transaction signature
            tx_data = f"{self.match_id}:{self.moves}:{self.winner}:{self.nonce}".encode()
            try:
                tx_pk.verify(base64.b64decode(self.signature), tx_data)
            except InvalidSignature:
                print(f"Invalid transaction signature for {self.nonce}")
                return False

            return True
        except Exception as e:
            print(f"Error verifying transaction {self.nonce}: {e}")
            return False