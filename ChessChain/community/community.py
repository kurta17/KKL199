import base64
import hashlib
import time
import uuid
from asyncio import create_task, sleep
from typing import Dict, List, Set, Tuple

import asyncio
import lmdb
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from ipv8.community import Community, CommunitySettings
from ipv8.types import Peer
from ipv8.messaging.serialization import default_serializer

from models.models import ChessTransaction, MoveData, ProposedBlockPayload, ProposerAnnouncement
from utils.utils import lottery_selection
from utils.merkle import MerkleTree
from .messages import on_transaction, on_proposed_block, on_proposer_announcement, on_move


class ChessCommunity(Community):
    """Community implementation for chess game transactions using IPv8."""
    
    community_id = b'chess_platform123456'

    INITIAL_STAKE = 120
    POS_ROUND_INTERVAL = 5
    MIN_STAKE = 10

    def __init__(self, settings: CommunitySettings) -> None:
        """Initialize the chess community."""
        super().__init__(settings)
        self.add_message_handler(ProposedBlockPayload, on_proposed_block)
        self.add_message_handler(ProposerAnnouncement, on_proposer_announcement)
        
        self.add_message_handler(ChessTransaction, on_transaction)
        self.add_message_handler(MoveData, on_move)
       
        # Set up databases
        self.db_env = lmdb.open('chess_db', max_dbs=3, map_size=10**8)
        self.tx_db = self.db_env.open_db(b'transactions')
        self.stake_db = self.db_env.open_db(b'stakes')
        self.moves_db = self.db_env.open_db(b'moves')
 
        # Initialize state
        self.transactions: Set[str] = set()
        self.mempool: Dict[str, ChessTransaction] = {}
        self.sent: Set[Tuple[bytes, str]] = set()
        self.stakes: Dict[bytes, int] = {}
        self.pos_round_number = 0
        self.current_round_seed = None
 
        # Load existing transactions and stakes
        with self.db_env.begin(db=self.tx_db) as tx:
            for key, _ in tx.cursor():
                self.transactions.add(key.decode())
        with self.db_env.begin(db=self.stake_db) as tx:
            for key, val in tx.cursor():
                self.stakes[key] = int(val.decode())
 
        # Generate keys for this peer
        self.sk = Ed25519PrivateKey.generate()
        self.pk = self.sk.public_key()
        self.pubkey_bytes = self.pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
       
        # Assign initial stake to this peer if it doesn't have any
        if self.pubkey_bytes not in self.stakes:
            self.stake_tokens(self.INITIAL_STAKE)

    
    def stake_tokens(self, amount: int) -> None:
        """Stake tokens in the system."""
        pid = self.pubkey_bytes
        new = self.stakes.get(pid, 0) + amount
        with self.db_env.begin(db=self.stake_db, write=True) as tx:
            tx.put(pid, str(new).encode())
        self.stakes[pid] = new
        print(f"Staked {amount}, total stake: {new}")
 
    def total_stake(self) -> int:
        """Calculate the total stake in the system."""
        return sum(self.stakes.values())

    def is_transaction_in_db(self, nonce: str) -> bool:
        """Check if a transaction with the given nonce exists in the LMDB database."""
        with self.db_env.begin(db=self.tx_db, write=False) as txn:
            return txn.get(nonce.encode('utf-8')) is not None

    def checking_proposer(self, seed: bytes) -> bytes:
        """Peer is checking if it is the proposer for a given seed."""
        return lottery_selection(seed_plus_id=seed + self.pubkey_bytes, my_stake=self.stakes[self.pubkey_bytes], total_stake=self.total_stake())

    def started(self) -> None:
        """Called when the community is started."""
        self.network.add_peer_observer(self)
        create_task(self.periodic_broadcast())
        create_task(self.pos_round())
 
    def on_peer_added(self, peer: Peer) -> None:
        """Called when a new peer is added."""
        print("New peer:", peer)
 
 
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
                    print(f"Error loading transaction {key_repr}: {e}")
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
                    print(f"Skipping non-UTF-8 key in moves_db: {key.hex()}")
                    continue
                except Exception as e:
                    key_repr = key.hex() if isinstance(key, bytes) else str(key)
                    print(f"Error loading move {key_repr}: {e}")
        return sorted(out, key=lambda x: x.id)
 
    async def periodic_broadcast(self) -> None:
        """Periodically broadcast transactions to peers."""
        while True:
            for tx in list(self.mempool.values()):
                for p in self.get_peers():
                    if p.mid != self.pubkey_bytes and (p.mid, tx.nonce) not in self.sent:
                        self.ez_send(p, tx)
                        self.sent.add((p.mid, tx.nonce))
            await sleep(5)
 
    def send_transaction(self, tx: ChessTransaction) -> None:
        """Send a verified transaction to peers."""
        if tx.nonce in self.transactions:
            print(f"Transaction {tx.nonce} already exists")
            return
        if not tx.verify_signatures():
            print(f"Transaction {tx.nonce} failed verification")
            return
        with self.db_env.begin(db=self.tx_db, write=True) as wr:
            serialized_tx = default_serializer.pack_serializable(tx)
            wr.put(tx.nonce.encode(), serialized_tx)
        self.transactions.add(tx.nonce)
        self.mempool[tx.nonce] = tx
        for p in self.get_peers():
            if p.mid != self.pubkey_bytes and (p.mid, tx.nonce) not in self.sent:
                self.ez_send(p, tx)
                self.sent.add((p.mid, tx.nonce))
        print(f"Sent transaction {tx.nonce}")
 
    async def send_moves(self, match_id: str, winner: str, moves: List[MoveData], nonce: str) -> None:
        """Send all moves for a completed match and the final transaction."""
        # Store and broadcast each move
        for move in moves:
            packed_move = default_serializer.pack_serializable(move)
            # Store move
            with self.db_env.begin(write=True) as txn:
                moves_db = self.db_env.open_db(b'moves', txn=txn, create=True)
                # Use a composite key: match_id + move_id
                move_key = f"{match_id}_{move.id}".encode('utf-8')
                txn.put(move_key, packed_move, db=moves_db)
            # Broadcast move (optional, depending on your P2P logic for moves)
            # self.ez_send(self.get_random_peer(), move) # Example, adjust as needed
            print(f"Sent move {move.id} for match {match_id}")
            await asyncio.sleep(0.1) # Simulate network delay or processing

        # Create and send the final transaction
        tx = ChessTransaction(
            match_id=match_id,
            winner=winner,
            moves_hash=",".join(str(m.id) for m in moves),  # Or a proper hash of moves
            nonce=nonce,
            proposer_pubkey_hex=self.my_peer.public_key.key_to_bin().hex() # Corrected: removed ()
        )

        # Sign the transaction
        tx_data_to_sign = f"{match_id}:{winner}:{nonce}:{self.my_peer.public_key.key_to_bin().hex()}".encode()
        tx.signature = self.my_peer.key.sign(tx_data_to_sign).hex()

        # Store and broadcast the transaction
        self.send_transaction(tx)
 
    def generate_fake_match(self) -> None:
        """Generate a fake match and start sending moves."""
        match_id = str(uuid.uuid4())
        winner = "player1" # Example winner
        nonce = str(uuid.uuid4()) # Unique nonce for the transaction

        # Define the sequence of moves
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
                player=move_def["player"], # Changed from player_id to player
                move=move_def["move"], # Changed from move_str to move
                timestamp=move_def["timestamp"],
                signature=move_signature_placeholder 
            )
            moves_list.append(move)
       
        self.logger.info(f"Generating fake match {match_id} with {len(moves_list)} moves. Winner: {winner}, Nonce: {nonce}")
        create_task(self.send_moves(match_id, winner, moves_list, nonce))
 
    async def pos_round(self) -> None:
        """Perform a round of PoS block proposal."""
        self.pos_round_number += 1
        current_time = time.time()
        self.logger.info(f"Starting PoS round {self.pos_round_number} at {current_time}")

        # Fetch transactions from storage (e.g., LMDB)
        stored_transactions = self.get_stored_transactions()
        transactions_to_propose: List[ChessTransaction] = []
        processed_nonces = set()

        for tx in stored_transactions:
            if tx.nonce not in processed_nonces:
                transactions_to_propose.append(tx)
                processed_nonces.add(tx.nonce)
        
        self.logger.info(f"Round {self.pos_round_number}: Fetched {len(transactions_to_propose)} transactions from DB.")

        # Add transactions from mempool that are not already included from DB
        mempool_tx_count = 0
        for nonce, tx_from_mempool in list(self.mempool.items()): 
            if nonce not in processed_nonces:
                if isinstance(tx_from_mempool, ChessTransaction):
                    transactions_to_propose.append(tx_from_mempool)
                    processed_nonces.add(nonce) 
                    mempool_tx_count += 1
                else:
                    self.logger.warning(f"Mempool item with nonce {nonce} is not a ChessTransaction object, but {type(tx_from_mempool)}. Skipping.")
        
        if mempool_tx_count > 0:
            self.logger.info(f"Round {self.pos_round_number}: Added {mempool_tx_count} unique transactions from mempool.")
        
        self.logger.info(f"Round {self.pos_round_number}: Total transactions to propose: {len(transactions_to_propose)}")

        if not transactions_to_propose:
            self.logger.info(f"Round {self.pos_round_number}: No transactions in mempool or DB to propose a block for.")
            await sleep(self.POS_ROUND_INTERVAL)
            return

        # Construct Merkle tree from transaction nonces
        transaction_hashes = [tx.nonce for tx in transactions_to_propose]
        if not transaction_hashes:
            self.logger.warning(f"Round {self.pos_round_number}: Transaction hashes list is empty despite having transactions. This should not happen.")
            await sleep(self.POS_ROUND_INTERVAL)
            return

        merkle_tree = MerkleTree(transaction_hashes)
        merkle_root = merkle_tree.get_root()
        if not merkle_root:
            self.logger.error(f"Round {self.pos_round_number}: Failed to generate Merkle root.")
            await sleep(self.POS_ROUND_INTERVAL)
            return

        self.logger.info(f"Round {self.pos_round_number}: Merkle root for {len(transaction_hashes)} transactions: {merkle_root}")

        # Create the proposed block payload
        round_seed_hex = self.current_round_seed.hex() if self.current_round_seed else "0" * 64
        proposer_pubkey_hex = self.pubkey_bytes.hex()

        block_data_to_sign_str = f"{round_seed_hex}:{merkle_root}:{proposer_pubkey_hex}"
        block_data_to_sign_bytes = block_data_to_sign_str.encode('utf-8')
        
        try:
            signature_hex = self.sk.sign(block_data_to_sign_bytes).hex()
        except Exception as e:
            self.logger.error(f"Round {self.pos_round_number}: Error signing block data: {e}")
            await sleep(self.POS_ROUND_INTERVAL)
            return

        proposed_block = ProposedBlockPayload(
            round_seed_hex=round_seed_hex,
            transaction_hashes=transaction_hashes,
            merkle_root=merkle_root,
            proposer_pubkey_hex=proposer_pubkey_hex,
            signature=signature_hex
        )

        self.logger.info(f"Round {self.pos_round_number}: Proposing block with Merkle root {merkle_root} and {len(transaction_hashes)} transactions.")
        for peer in self.get_peers():
            self.ez_send(peer, proposed_block)
        
        for tx_nonce in transaction_hashes:
            if tx_nonce in self.mempool:
                del self.mempool[tx_nonce]
        self.logger.info(f"Round {self.pos_round_number}: Cleared {len(transaction_hashes)} proposed transactions from mempool.")

        await sleep(self.POS_ROUND_INTERVAL)
