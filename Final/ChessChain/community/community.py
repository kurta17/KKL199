import asyncio
from asyncio import create_task
import time
from typing import List
from ipv8.community import Community, CommunitySettings
from ipv8.lazy_community import lazy_wrapper
from ipv8.types import Peer
from .datamanage import DataManager
from .consensus import ConsensusManager
from models.models import ChessTransaction, MoveData, ProposedBlockPayload, ProposerAnnouncement, ValidatorVote, BlockConfirmation, BlockSyncRequest, BlockSyncResponse

class ChessCommunity(Community):
    """Community implementation for chess game transactions using IPv8."""
    
    community_id = b'chess_platform123456'
    INITIAL_STAKE = 120
    POS_ROUND_INTERVAL = 20
    MIN_STAKE = 10
    
    def __init__(self, settings: CommunitySettings) -> None:
        """Initialize the chess community."""
        super().__init__(settings)
        
        # Initialize managers, passing the logger
        self.data_manager = DataManager('chess_db', logger=self.logger)
        self.consensus_manager = ConsensusManager(self, self.data_manager, logger=self.logger)
        
        # Register message handlers
        self.add_message_handler(ChessTransaction, self.on_transaction)
        self.add_message_handler(MoveData, self.on_move)
        self.add_message_handler(ProposedBlockPayload, self.on_proposed_block)
        self.add_message_handler(ProposerAnnouncement, self.on_proposer_announcement)
        self.add_message_handler(ValidatorVote, self.on_validator_vote)
        self.add_message_handler(BlockConfirmation, self.on_block_confirmation)
        self.add_message_handler(BlockSyncRequest, self.on_block_sync_request)
        self.add_message_handler(BlockSyncResponse, self.on_block_sync_response)
        
        # Start periodic tasks
        self.network.add_peer_observer(self)
        create_task(self.periodic_broadcast())
        create_task(self.startup_sequence())
    
    def started(self) -> None:
        """Called when the community is started."""
        pass  # Handled in __init__ via create_task
    
    async def startup_sequence(self) -> None:
        """Handles the node startup sequence with synchronization."""
        self.logger.info("Node starting up. Beginning startup sequence...")
        start_time = time.time()
        peer_discovery_time = 50
        while time.time() - start_time < peer_discovery_time:
            peers = self.get_peers()
            if peers:
                self.logger.info(f"Found {len(peers)} peers. Continuing startup sequence.")
                break
            await asyncio.sleep(2)
        
        peers = self.get_peers()
        if not peers:
            self.logger.warning("No peers found during discovery period. Operating in standalone mode.")
        else:
            self.logger.info(f"Beginning blockchain synchronization with {len(peers)} peers...")
            if await self.consensus_manager.sync_blockchain_data():
                self.logger.info("Blockchain synchronization completed successfully.")
            else:
                self.logger.warning("Blockchain synchronization incomplete. Using local state.")
        
        self.logger.info("Starting PoS consensus rounds...")
        create_task(self.consensus_manager.pos_round())
    
    async def periodic_broadcast(self) -> None:
        """Periodically broadcast transactions to peers."""
        while True:
            for tx in list(self.data_manager.get_mempool().values()):
                for p in self.get_peers():
                    if p.mid != self.data_manager.pubkey_bytes and (p.mid, tx.nonce) not in self.data_manager.sent:
                        self.ez_send(p, tx)
                        self.data_manager.sent.add((p.mid, tx.nonce))
            await asyncio.sleep(5)
    
    @lazy_wrapper(ChessTransaction)
    def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
        """Handle incoming transactions."""
        self.data_manager.handle_transaction(peer, payload)
    
    @lazy_wrapper(MoveData)
    def on_move(self, peer: Peer, payload: MoveData) -> None:
        """Handle incoming move messages."""
        self.data_manager.store_move(peer, payload)
    
    @lazy_wrapper(ProposedBlockPayload)
    async def on_proposed_block(self, peer: Peer, payload: ProposedBlockPayload) -> None:
        """Handle incoming proposed blocks."""
        await self.consensus_manager.handle_proposed_block(peer, payload)
    
    @lazy_wrapper(ProposerAnnouncement)
    async def on_proposer_announcement(self, peer: Peer, payload: ProposerAnnouncement) -> None:
        """Handle proposer announcements."""
        self.logger.info(f"Received ProposerAnnouncement for round {payload.round_seed_hex[:8]} from {payload.proposer_pubkey_hex[:8]} (peer {peer.mid.hex()[:8]})")
    
    @lazy_wrapper(ValidatorVote)
    async def on_validator_vote(self, peer: Peer, payload: ValidatorVote) -> None:
        """Handle incoming validator votes."""
        await self.consensus_manager.handle_validator_vote(peer, payload)
    
    @lazy_wrapper(BlockConfirmation)
    async def on_block_confirmation(self, peer: Peer, payload: BlockConfirmation) -> None:
        """Handle incoming block confirmations."""
        await self.consensus_manager.handle_block_confirmation(peer, payload)
    
    @lazy_wrapper(BlockSyncRequest)
    async def on_block_sync_request(self, peer: Peer, payload: BlockSyncRequest) -> None:
        """Handle block sync requests."""
        await self.consensus_manager.handle_block_sync_request(peer, payload)
    
    @lazy_wrapper(BlockSyncResponse)
    async def on_block_sync_response(self, peer: Peer, payload: BlockSyncResponse) -> None:
        """Handle block sync responses."""
        await self.consensus_manager.handle_block_sync_response(peer, payload)
    
    def on_peer_added(self, peer: Peer) -> None:
        """Called when a new peer is added."""
        self.logger.info(f"New peer: {peer}")
    
    def send_transaction(self, tx: ChessTransaction) -> None:
        """Send a verified transaction to peers."""
        self.data_manager.send_transaction(self, tx)
    
    async def send_moves(self, match_id: str, winner: str, moves: List[MoveData], nonce: str) -> None:
        """Send moves and final transaction for a match."""
        await self.data_manager.send_moves(self, match_id, winner, moves, nonce)
    
    def generate_fake_match(self) -> None:
        """Generate a fake match for testing."""
        self.data_manager.generate_fake_match(self)