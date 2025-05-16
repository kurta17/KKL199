import asyncio
import time
import uuid
from typing import List
from .community0 import ChessCommunity
from models.models import MoveData, ChessTransaction
from ipv8.messaging.serialization import default_serializer
from ipv8.types import Peer

class Moves:
    def __init__(self, community: ChessCommunity):
        self.community = community
        self.logger = community.logger
        self.db_env = community.db_env
        self.moves_db = community.moves_db
        self.sk = community.sk
        self.pubkey_bytes = community.pubkey_bytes

    def on_move(self, peer: Peer, payload: MoveData) -> None:
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

    async def send_moves(self, match_id: str, winner: str, moves: List[MoveData], nonce: str) -> None:
        for move in moves:
            packed_move = default_serializer.pack_serializable(move)
            with self.db_env.begin(write=True) as txn:
                moves_db = self.db_env.open_db(b'moves', txn=txn, create=True)
                move_key = f"{match_id}_{move.id}".encode('utf-8')
                txn.put(move_key, packed_move, db=moves_db)
            print(f"Sent move {move.id} for match {match_id}")
            await asyncio.sleep(0.1)
        proposer_pubkey_hex = self.pubkey_bytes.hex()
        tx_data_to_sign = f"{match_id}:{winner}:{nonce}:{proposer_pubkey_hex}".encode()
        try:
            transaction_signature_hex = self.sk.sign(tx_data_to_sign).hex()
        except Exception as e:
            self.logger.error(f"Error signing transaction data for match {match_id}, nonce {nonce}: {e}")
            return
        tx = ChessTransaction(
            match_id=match_id,
            winner=winner,
            moves_hash=",".join(str(m.id) for m in moves),
            nonce=nonce,
            proposer_pubkey_hex=proposer_pubkey_hex,
            signature=transaction_signature_hex
        )
        self.community.transaction.send_transaction(tx)

    def generate_fake_match(self) -> None:
        match_id = str(uuid.uuid4())
        winner = "player1"
        nonce = str(uuid.uuid4())
        raw_move_definitions = [
            {"id": 1, "player": "player1_pubkey_hex", "move": "e4", "timestamp": time.time()},
            {"id": 2, "player": "player2_pubkey_hex", "move": "e5", "timestamp": time.time() + 1},
            {"id": 3, "player": "player1_pubkey_hex", "move": "Nf3", "timestamp": time.time() + 2}
        ]
        moves_list: List[MoveData] = []
        for move_def in raw_move_definitions:
            move_signature_placeholder = "fake_signature_" + str(move_def["id"])
            move = MoveData(
                match_id=match_id,
                id=move_def["id"],
                player=move_def["player"],
                move=move_def["move"],
                timestamp=move_def["timestamp"],
                signature=move_signature_placeholder
            )
            moves_list.append(move)
        self.logger.info(f"Generating fake match {match_id} with {len(moves_list)} moves. Winner: {winner}, Nonce: {nonce}")
        asyncio.create_task(self.send_moves(match_id, winner, moves_list, nonce))

    def get_stored_moves(self, match_id: str) -> List[MoveData]:
        out = []
        with self.db_env.begin(db=self.moves_db) as txn:
            cursor = txn.cursor()
            for key, raw in cursor:
                try:
                    key_str = key.decode()
                    if key_str.startswith(f"{match_id}_"):
                        deserialized_move, _ = default_serializer.unpack_serializable(MoveData, raw)
                        out.append(deserialized_move)
                except UnicodeDecodeError:
                    print(f"Skipping non-UTF-8 key in moves_db: {key.hex()}")
                    continue
                except Exception as e:
                    key_repr = key.hex() if isinstance(key, bytes) else str(key)
                    print(f"Error loading move {key_repr}: {e}")
        return sorted(out, key=lambda x: x.id)