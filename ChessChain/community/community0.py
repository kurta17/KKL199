import base64
import hashlib
import time
import uuid
from asyncio import create_task, sleep
from typing import Dict, List, Set, Tuple
from ipv8.lazy_community import lazy_wrapper
from cryptography.exceptions import InvalidSignature 
from models.models import BlockSyncRequest, BlockSyncResponse, ChessTransaction, MoveData, ProposedBlockPayload, ProposerAnnouncement, ValidatorVote, BlockConfirmation
import asyncio
import lmdb
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from ipv8.community import Community, CommunitySettings
from ipv8.types import Peer
from ipv8.messaging.serialization import default_serializer
from utils.utils import lottery_selection
from utils.merkle import MerkleTree
from ipv8.messaging.payload_dataclass import DataClassPayload, Serializable
from .blockchain import Blockchain
from .consensus import Consensus
from .sync import Sync
from .transaction import Transaction
from .moves import Moves
from .proposer import Proposer
from .stake import Stake
# Update the import to use the renamed class
from .network import ChessNetwork

class ChessCommunity(Community):
    """Community implementation for chess game transactions using IPv8."""
    
    community_id = b'chess_platform123456'
    INITIAL_STAKE = 120
    POS_ROUND_INTERVAL = 20
    MIN_STAKE = 10
    MAX_BLOCK_AGE = 3600  # 1 hour
    SYNC_TIMEOUT = 60     # 1 minute
    QUORUM_RATIO = 0.67   # 2/3 majority for consensus
    GENESIS_PUBKEY_HEX = "..."  # The hex of the fixed genesis public key
    GENESIS_SIGNATURE = "..."   # The hex signature for the genesis block
    GENESIS_TIME = 1714501200
    GENESIS_SEED = "000000..."  # as before

    def __init__(self, settings: CommunitySettings) -> None:
        """Initialize the chess community."""
        super().__init__(settings)
        self.add_message_handler(ProposedBlockPayload, self.on_proposed_block)
        self.add_message_handler(ProposerAnnouncement, self.on_proposer_announcement)
        self.add_message_handler(ChessTransaction, self.on_transaction)
        self.add_message_handler(MoveData, self.on_move)
        self.add_message_handler(ValidatorVote, self.on_validator_vote)
        self.add_message_handler(BlockConfirmation, self.on_block_confirmation)
        self.add_message_handler(BlockSyncRequest, self.on_block_sync_request)
        self.add_message_handler(BlockSyncResponse, self.on_block_sync_response)

        # Set up databases
        self.db_env = lmdb.open('chess_db', max_dbs=128, map_size=10**8)
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
        self.pending_transactions: Dict[str, ChessTransaction] = {}
        self.round_proposers: Dict[str, str] = {}
        self.block_votes: Dict[str, Dict[str, bool]] = {}
        self.block_confirmations: Dict[str, BlockConfirmation] = {}
        self.processed_blocks: Set[str] = set()
        self.current_chain_head = None
        self.pending_sync_requests = {}

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
            self.stake = Stake(self)
            self.stake.stake_tokens(self.INITIAL_STAKE)

        # Initialize modules
        self.blockchain = Blockchain(self)
        self.consensus = Consensus(self)
        self.sync = Sync(self)
        self.transaction = Transaction(self)
        self.moves = Moves(self)
        self.proposer = Proposer(self)
        self.stake = Stake(self)
        self.chess_network = ChessNetwork(self)

        self.blockchain.initialize_blockchain()

    # Message handlers
    @lazy_wrapper(ProposedBlockPayload)
    async def on_proposed_block(self, peer: Peer, payload: ProposedBlockPayload) -> None:
        await self.proposer.on_proposed_block(peer, payload)

    @lazy_wrapper(ProposerAnnouncement)
    async def on_proposer_announcement(self, peer: Peer, payload: ProposerAnnouncement) -> None:
        await self.proposer.on_proposer_announcement(peer, payload)

    @lazy_wrapper(ChessTransaction)
    def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
        self.transaction.on_transaction(peer, payload)

    @lazy_wrapper(MoveData)
    def on_move(self, peer: Peer, payload: MoveData) -> None:
        self.moves.on_move(peer, payload)

    @lazy_wrapper(ValidatorVote)
    async def on_validator_vote(self, peer: Peer, payload: ValidatorVote) -> None:
        await self.consensus.on_validator_vote(peer, payload)

    @lazy_wrapper(BlockConfirmation)
    async def on_block_confirmation(self, peer: Peer, payload: BlockConfirmation) -> None:
        await self.consensus.on_block_confirmation(peer, payload)

    @lazy_wrapper(BlockSyncRequest)
    async def on_block_sync_request(self, peer: Peer, payload: BlockSyncRequest) -> None:
        await self.sync.on_block_sync_request(peer, payload)

    @lazy_wrapper(BlockSyncResponse)
    async def on_block_sync_response(self, peer: Peer, payload: BlockSyncResponse) -> None:
        await self.sync.on_block_sync_response(peer, payload)

    def started(self) -> None:
        """Called when the community is started."""
        # Create a task to run the startup sequence asynchronously
        asyncio.create_task(self.chess_network.startup_sequence())
    
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
        """Get all moves for a given match_id from the database.
        
        Args:
            match_id: The ID of the match to retrieve moves for
            
        Returns:
            List of MoveData objects for the specified match, sorted by move ID
        """
        out = []
        match_prefix = f"{match_id}:"  # Using the match_id: prefix for composite keys
        
        with self.db_env.begin(db=self.moves_db) as txn:
            cursor = txn.cursor()
            
            # First try with the composite key format: match_id:move_id
            for key, raw in cursor:
                try:
                    key_str = key.decode()
                    if key_str.startswith(match_prefix):
                        deserialized_move, _ = default_serializer.unpack_serializable(MoveData, raw)
                        out.append(deserialized_move)
                except Exception as e:
                    key_repr = key.hex() if isinstance(key, bytes) else str(key)
                    print(f"Error loading move {key_repr}: {e}")
            
            # If no moves found with composite key, try legacy key format: match_id_move_id
            if not out:
                legacy_prefix = f"{match_id}_"
                cursor.first()  # Reset cursor
                for key, raw in cursor:
                    try:
                        key_str = key.decode()
                        if key_str.startswith(legacy_prefix):
                            deserialized_move, _ = default_serializer.unpack_serializable(MoveData, raw)
                            out.append(deserialized_move)
                    except Exception as e:
                        key_repr = key.hex() if isinstance(key, bytes) else str(key)
                        print(f"Error loading move with legacy key {key_repr}: {e}")
        
        # Sort moves by ID to ensure correct ordering
        return sorted(out, key=lambda x: x.id)

    def generate_fake_match(self) -> None:
        """Generate a fake match and start sending moves."""
        import uuid
        from asyncio import create_task
        
        match_id = str(uuid.uuid4())
        winner = "player1"  # Example winner
        nonce = str(uuid.uuid4())  # Unique nonce for the transaction

        # Define the sequence of moves
        current_time = time.time()
        raw_move_definitions = [
            {"id": 1, "player": "player1_pubkey_hex", "move": "e4", "timestamp": current_time},
            {"id": 2, "player": "player2_pubkey_hex", "move": "e5", "timestamp": current_time + 1},
            {"id": 3, "player": "player1_pubkey_hex", "move": "Nf3", "timestamp": current_time + 2},
            {"id": 4, "player": "player2_pubkey_hex", "move": "Nc6", "timestamp": current_time + 3},
            {"id": 5, "player": "player1_pubkey_hex", "move": "Bc4", "timestamp": current_time + 4}
        ]

        moves_list = []
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
        
        # Check if send_moves exists, otherwise define it
        if hasattr(self, 'send_moves'):
            create_task(self.send_moves(match_id, winner, moves_list, nonce))
        else:
            self.logger.error("Cannot send moves: 'send_moves' method not found in ChessCommunity")
            print("Missing send_moves method in ChessCommunity class. Please implement it first.")
            
    async def send_moves(self, match_id: str, winner: str, moves: List[MoveData], nonce: str) -> None:
        """Send a sequence of moves as a transaction."""
        import hashlib
        from ipv8.messaging.serialization import default_serializer
        
        self.logger.info(f"Sending {len(moves)} moves for match {match_id}")
        
        # Process each move
        for move in moves:
            # Sign the move with our private key
            move_data = f"{match_id}:{move.id}:{move.player}:{move.move}:{move.timestamp}".encode()
            move.signature = self.sk.sign(move_data).hex()
            
            # Broadcast the move to peers
            self.logger.info(f"Broadcasting move: {move.move} (ID: {move.id})")
            peers = self.network.get_peers_for_service(self.community_id)
            if peers:
                for peer in peers:
                    self.ez_send(peer, move)
            else:
                self.logger.warning("No peers available to send moves to")
            
            # Simulate delay between moves
            await asyncio.sleep(0.5)
        
        # Create a hash of all moves
        moves_hash = hashlib.sha256(''.join([f"{m.id}:{m.move}" for m in moves]).encode()).hexdigest()
        
        # Create and send the transaction
        tx_data = f"{match_id}:{winner}:{nonce}:{self.pubkey_bytes.hex()}".encode()
        tx_signature = self.sk.sign(tx_data).hex()
        
        transaction = ChessTransaction(
            match_id=match_id,
            winner=winner,
            moves_hash=moves_hash,
            nonce=nonce,
            proposer_pubkey_hex=self.pubkey_bytes.hex(),
            signature=tx_signature
        )
        
        # Add to mempool and broadcast
        self.transaction.add_to_mempool(transaction)
        
        peers = self.network.get_peers_for_service(self.community_id)
        if peers:
            for peer in peers:
                self.ez_send(peer, transaction)
            self.logger.info(f"Sent transaction for match {match_id} with {len(moves)} moves to {len(peers)} peers")
        else:
            self.logger.warning("No peers available to send transaction to")