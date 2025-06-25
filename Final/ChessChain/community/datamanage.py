import uuid
import time
from typing import Dict, List, Set, Tuple
from logging import Logger
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
import lmdb
import asyncio
import hashlib
from ipv8.messaging.serialization import default_serializer
from ipv8.types import Peer
from models.models import ChessTransaction, MoveData
from utils.merkle import MerkleTree

class DataManager:
    """Manages data storage and retrieval for the chess community."""
    
    def __init__(self, db_path: str, logger: Logger) -> None:
        """Initialize the data manager."""
        self.logger = logger
        self.db_env = lmdb.open(db_path, max_dbs=128, map_size=10**8)
        self.tx_db = self.db_env.open_db(b'transactions')
        self.stake_db = self.db_env.open_db(b'stakes')
        self.moves_db = self.db_env.open_db(b'moves')
        self.processed_db = self.db_env.open_db(b'processed_transactions', create=True)
        
        # Initialize state
        self.transactions: Set[str] = set()
        self.mempool: Dict[str, ChessTransaction] = {}
        self.sent: Set[Tuple[bytes, str]] = set()
        self.stakes: Dict[bytes, int] = {}
        self.pending_transactions: Dict[str, ChessTransaction] = {}
        
        # Load existing data
        with self.db_env.begin(db=self.tx_db) as tx:
            for key, _ in tx.cursor():
                self.transactions.add(key.decode())
        with self.db_env.begin(db=self.stake_db) as tx:
            for key, val in tx.cursor():
                self.stakes[key] = int(val.decode())
        
        # Generate keys
        self.sk = Ed25519PrivateKey.generate()
        self.pk = self.sk.public_key()
        self.pubkey_bytes = self.pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        if self.pubkey_bytes not in self.stakes:
            self.stake_tokens(120)
    
    def stake_tokens(self, amount: int) -> None:
        """Stake tokens for this peer."""
        pid = self.pubkey_bytes
        new = self.stakes.get(pid, 0) + amount
        with self.db_env.begin(db=self.stake_db, write=True) as tx:
            tx.put(pid, str(new).encode())
        self.stakes[pid] = new
        print(f"Staked {amount}, total stake: {new}")
    
    def total_stake(self) -> int:
        """Calculate total stake."""
        return sum(self.stakes.values())
    
    def is_transaction_in_db(self, nonce: str) -> bool:
        """Check if a transaction exists in the database."""
        with self.db_env.begin(db=self.tx_db) as txn:
            return txn.get(nonce.encode('utf-8')) is not None
    
    def get_mempool(self) -> Dict[str, ChessTransaction]:
        """Return the current mempool."""
        return self.mempool
    
    def get_stored_transactions(self) -> List[ChessTransaction]:
        """Get all transactions stored in the database."""
        out = []
        with self.db_env.begin(db=self.tx_db) as txn:
            for key, raw in txn.cursor():
                try:
                    deserialized_tx, _ = default_serializer.unpack_serializable(ChessTransaction, raw)
                    out.append(deserialized_tx)
                except Exception as e:
                    key_repr = key.hex() if isinstance(key, bytes) else str(key)
                    self.logger.error(f"Error loading transaction {key_repr}: {e}")
        return out
    
    def get_stored_moves(self, match_id: str) -> List[MoveData]:
        """Get all moves for a given match_id from the database."""
        out = []
        with self.db_env.begin(db=self.moves_db) as txn:
            cursor = txn.cursor()
            for key, raw in cursor:
                try:
                    key_str = key.decode()
                    if key_str.startswith(f"{match_id}:"):
                        deserialized_move, _ = default_serializer.unpack_serializable(MoveData, raw)
                        out.append(deserialized_move)
                except UnicodeDecodeError:
                    self.logger.warning(f"Skipping non-UTF-8 key in moves_db: {key.hex()}")
                    continue
                except Exception as e:
                    key_repr = key.hex() if isinstance(key, bytes) else str(key)
                    self.logger.error(f"Error loading move {key_repr}: {e}")
        return sorted(out, key=lambda x: x.id)
    
    def get_unprocessed_transactions(self) -> List[ChessTransaction]:
        """Get transactions not yet in a block."""
        out = []
        with self.db_env.begin(db=self.tx_db) as txn:
            with self.db_env.begin(db=self.processed_db) as processed_txn:
                for key, raw in txn.cursor():
                    if processed_txn.get(key) is None:
                        try:
                            deserialized_tx, _ = default_serializer.unpack_serializable(ChessTransaction, raw)
                            out.append(deserialized_tx)
                        except Exception as e:
                            key_repr = key.hex() if isinstance(key, bytes) else str(key)
                            self.logger.error(f"Error loading transaction {key_repr}: {e}")
        return out
    
    def mark_transactions_as_processed(self, transaction_hashes: List[str]) -> None:
        """Mark transactions as processed."""
        with self.db_env.begin(db=self.processed_db, write=True) as txn:
            for tx_hash in transaction_hashes:
                txn.put(tx_hash.encode(), b'1')
                if tx_hash in self.pending_transactions:
                    del self.pending_transactions[tx_hash]
                if tx_hash in self.mempool:
                    del self.mempool[tx_hash]
    
    def create_dummy_transactions(self, count: int) -> None:
        """Create dummy transactions for initial blockchain setup."""
        for i in range(count):
            nonce = hashlib.sha256(f"dummy_tx_{i}_{time.time()}".encode()).hexdigest()
            match_id = f"dummy_match_{i}"
            winner = "dummy_winner"
            moves_hash = "dummy_moves"
            data = f"{match_id}:{winner}:{nonce}:{self.pubkey_bytes.hex()}".encode()
            signature = self.sk.sign(data).hex()
            tx = ChessTransaction(
                match_id=match_id,
                winner=winner,
                moves_hash=moves_hash,
                nonce=nonce,
                proposer_pubkey_hex=self.pubkey_bytes.hex(),
                signature=signature
            )
            packed_tx = default_serializer.pack_serializable(tx)
            with self.db_env.begin(db=self.tx_db, write=True) as txn:
                txn.put(nonce.encode(), packed_tx)
            self.transactions.add(nonce)
            self.mempool[nonce] = tx
    
    def handle_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
        """Handle and store an incoming transaction."""
        try:
            pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.proposer_pubkey_hex))
            data = f"{payload.match_id}:{payload.winner}:{payload.nonce}:{payload.proposer_pubkey_hex}".encode()
            pubkey.verify(bytes.fromhex(payload.signature), data)
            self.logger.info(f"Transaction {payload.nonce} signature verified.")
        except InvalidSignature:
            self.logger.warning(f"Transaction {payload.nonce} signature invalid.")
            return
        except Exception as e:
            self.logger.error(f"Error verifying transaction {payload.nonce}: {e}")
            return
        
        if payload.nonce in self.mempool or self.is_transaction_in_db(payload.nonce):
            self.logger.info(f"Transaction {payload.nonce} already processed or in mempool.")
            return
        
        self.mempool[payload.nonce] = payload
        try:
            packed_tx = default_serializer.pack_serializable(payload)
            with self.db_env.begin(db=self.tx_db, write=True) as txn:
                txn.put(payload.nonce.encode('utf-8'), packed_tx)
            self.logger.info(f"Stored transaction {payload.nonce} from {peer.mid.hex()[:8]}")
        except Exception as e:
            self.logger.error(f"Failed to store transaction {payload.nonce}: {e}")
            if payload.nonce in self.mempool:
                del self.mempool[payload.nonce]
    
    def store_move(self, peer: Peer, payload: MoveData) -> None:
        """Store an incoming move."""
        packed_move = default_serializer.pack_serializable(payload)
        key = f"{payload.match_id}:{payload.id}".encode()
        try:
            with self.db_env.begin(db=self.moves_db, write=True) as txn:
                if txn.get(key):
                    self.logger.info(f"Move {payload.id} for match {payload.match_id} already exists.")
                    return
                txn.put(key, packed_move)
            self.logger.info(f"Stored move {payload.id} for match {payload.match_id} from {peer.mid.hex()[:8]}")
        except Exception as e:
            self.logger.error(f"Error storing move {payload.id} for match {payload.match_id}: {e}")
    
    def send_transaction(self, community: 'ChessCommunity', tx: ChessTransaction) -> None:
        """Store and broadcast a transaction."""
        if tx.nonce in self.transactions:
            self.logger.info(f"Transaction {tx.nonce} already exists")
            return
        try:
            pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(tx.proposer_pubkey_hex))
            data = f"{tx.match_id}:{tx.winner}:{tx.nonce}:{tx.proposer_pubkey_hex}".encode()
            pubkey.verify(bytes.fromhex(tx.signature), data)
        except InvalidSignature:
            self.logger.warning(f"Transaction {tx.nonce} failed verification")
            return
        
        try:
            packed_tx = default_serializer.pack_serializable(tx)
            with self.db_env.begin(db=self.tx_db, write=True) as txn:
                txn.put(tx.nonce.encode(), packed_tx)
            self.transactions.add(tx.nonce)
            self.mempool[tx.nonce] = tx
            for p in community.get_peers():
                if p.mid != self.pubkey_bytes and (p.mid, tx.nonce) not in self.sent:
                    community.ez_send(p, tx)
                    self.sent.add((p.mid, tx.nonce))
            self.logger.info(f"Sent transaction {tx.nonce}")
        except Exception as e:
            self.logger.error(f"Failed to process transaction {tx.nonce}: {e}")
    
    async def send_moves(self, community: 'ChessCommunity', match_id: str, winner: str, moves: List[MoveData], nonce: str) -> None:
        """Send moves and final transaction."""
        for move in moves:
            packed_move = default_serializer.pack_serializable(move)
            key = f"{match_id}_{move.id}".encode()
            try:
                with self.db_env.begin(db=self.moves_db, write=True) as txn:
                    txn.put(key, packed_move)
                self.logger.info(f"Sent move {move.id} for match {match_id}")
                await asyncio.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error storing move {move.id} for match {match_id}: {e}")
        
        data = f"{match_id}:{winner}:{nonce}:{self.pubkey_bytes.hex()}".encode()
        try:
            signature = self.sk.sign(data).hex()
            tx = ChessTransaction(
                match_id=match_id,
                winner=winner,
                moves_hash=",".join(str(m.id) for m in moves),
                nonce=nonce,
                proposer_pubkey_hex=self.pubkey_bytes.hex(),
                signature=signature
            )
            self.send_transaction(community, tx)
        except Exception as e:
            self.logger.error(f"Error signing transaction for match {match_id}, nonce {nonce}: {e}")
    
    def generate_fake_match(self, community: 'ChessCommunity') -> None:
        """Generate a fake match for testing."""
        match_id = str(uuid.uuid4())
        winner = "player1"
        nonce = str(uuid.uuid4())
        raw_move_definitions = [
            {"id": 1, "player": "player1_pubkey_hex", "move": "e4", "timestamp": time.time()},
            {"id": 2, "player": "player2_pubkey_hex", "move": "e5", "timestamp": time.time() + 1},
            {"id": 3, "player": "player1_pubkey_hex", "move": "Nf3", "timestamp": time.time() + 2}
        ]
        moves = [
            MoveData(
                match_id=match_id,
                id=move_def["id"],
                player=move_def["player"],
                move=move_def["move"],
                timestamp=move_def["timestamp"],
                signature="fake_signature_" + str(move_def["id"])
            ) for move_def in raw_move_definitions
        ]
        self.logger.info(f"Generating fake match {match_id} with {len(moves)} moves.")
        asyncio.create_task(self.send_moves(community, match_id, winner, moves, nonce))