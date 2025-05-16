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
from .network import Network

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
        self.network = Network(self)

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
        self.network.startup_sequence()