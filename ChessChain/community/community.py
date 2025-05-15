import base64
import hashlib
import time
import uuid
from asyncio import create_task, sleep
from typing import Dict, List, Set, Tuple
from ipv8.lazy_community import lazy_wrapper
from cryptography.exceptions import InvalidSignature 
from models.models import BlockSyncRequest, BlockSyncResponse

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
from ipv8.messaging.payload_dataclass import DataClassPayload, Serializable





class ChessCommunity(Community):
    """Community implementation for chess game transactions using IPv8."""
    
    community_id = b'chess_platform123456'

    INITIAL_STAKE = 120
    POS_ROUND_INTERVAL = 20
    MIN_STAKE = 10

    def __init__(self, settings: CommunitySettings) -> None:
        """Initialize the chess community."""
        super().__init__(settings)
        self.add_message_handler(ProposedBlockPayload, self.on_proposed_block)
        self.add_message_handler(ProposerAnnouncement, self.on_proposer_announcement)
        
        self.add_message_handler(ChessTransaction, self.on_transaction)
        self.add_message_handler(MoveData, self.on_move)
        
        # Add handlers for the validation messages
        from models.models import ValidatorVote, BlockConfirmation
        self.add_message_handler(ValidatorVote, self.on_validator_vote)
        self.add_message_handler(BlockConfirmation, self.on_block_confirmation)
       
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
        self.pending_transactions: Dict[str, ChessTransaction] = {}  # Transactions in proposed blocks awaiting confirmation
        
        # Consensus tracking dictionaries
        self.round_proposers: Dict[str, str] = {}  # Maps round seed to proposer pubkey
        self.block_votes: Dict[str, Dict[str, bool]] = {}  # Maps block_id to {validator_pubkey: vote}
        self.block_confirmations: Dict[str, BlockConfirmation] = {}  # Maps block_id to confirmation
        self.processed_blocks: Set[str] = set()  # Set of already processed block IDs
        
        # Consensus parameters
        self.QUORUM_RATIO = 0.67  # 2/3 majority for consensus
 
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


        self.current_chain_head = None
        self.initialize_blockchain()

        # Add handlers for block synchronization
        self.add_message_handler(BlockSyncRequest, self.on_block_sync_request)
        self.add_message_handler(BlockSyncResponse, self.on_block_sync_response)
        
        # Track pending sync requests
        self.pending_sync_requests = {}

    async def resolve_fork_with_retry(self, block: ProposedBlockPayload) -> bool:
        """Resolve a fork with block synchronization if needed."""
        # First try normal resolution
        fork_resolved = self.resolve_fork(block)
        
        # If that fails due to missing blocks, request them
        if not fork_resolved:
            self.logger.info(f"Normal fork resolution failed. Requesting blocks from peer chain...")
            
            # Find peers that might have this block's chain
            for peer in self.get_peers():
                # Store this block info for when response arrives
                self.pending_sync_requests[block.previous_block_hash] = block
                
                # Send sync request
                request = BlockSyncRequest(block.previous_block_hash)
                self.ez_send(peer, request)
                self.logger.info(f"Sent block sync request for {block.previous_block_hash[:16]} to {peer.mid.hex()[:8]}")
            
            return False  # Still not resolved, waiting for sync
        
        return True  # Fork resolved

    @lazy_wrapper(BlockSyncRequest)
    async def on_block_sync_request(self, peer: Peer, payload: BlockSyncRequest) -> None:
        """Handle requests for block synchronization."""
        self.logger.info(f"Received block sync request for {payload.block_hash[:16]} from {peer.mid.hex()[:8]}")
        
        # Get the requested blocks
        blocks = {}
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        
        with self.db_env.begin(db=blocks_db) as txn:
            # Start with the requested block
            current_hash = payload.block_hash
            count = 0
            
            while current_hash and count < payload.count:
                block_data = txn.get(current_hash.encode('utf-8'))
                if not block_data:
                    break
                    
                blocks[current_hash] = block_data.hex()
                count += 1
                
                # Get the previous block hash to follow the chain backwards
                try:
                    block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                    current_hash = block.previous_block_hash
                except Exception as e:
                    self.logger.error(f"Error deserializing block during sync: {e}")
                    break
        
        # Serialize the blocks data as JSON
        import json
        blocks_data = json.dumps(blocks)
        
        # Send the response
        response = BlockSyncResponse(payload.block_hash, blocks_data)
        self.ez_send(peer, response)
        self.logger.info(f"Sent {len(blocks)} blocks in sync response to {peer.mid.hex()[:8]}")

    @lazy_wrapper(BlockSyncResponse) 
    async def on_block_sync_response(self, peer: Peer, payload: BlockSyncResponse) -> None:
        """Handle responses to block synchronization requests."""
        self.logger.info(f"Received block sync response for {payload.request_hash[:16]} with blocks")
        
        # Track sync response for startup sequence
        if not hasattr(self, 'sync_responses_received'):
            self.sync_responses_received = 0
        self.sync_responses_received += 1
        
        # Deserialize the blocks data
        try:
            blocks = json.loads(payload.blocks_data)
            self.logger.info(f"Received {len(blocks)} blocks in sync response")
            
            # Store the received blocks
            blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
            
            new_blocks_count = 0
            with self.db_env.begin(db=blocks_db, write=True) as txn:
                for block_hash, block_data_hex in blocks.items():
                    # Skip if we already have this block
                    if txn.get(block_hash.encode('utf-8')):
                        continue
                        
                    block_data = bytes.fromhex(block_data_hex)
                    txn.put(block_hash.encode('utf-8'), block_data)
                    new_blocks_count += 1
                    
            self.logger.info(f"Stored {new_blocks_count} new blocks in database")
            
            # If we received new blocks, consider sync successful
            if new_blocks_count > 0:
                self.sync_complete = True
                # Update our chain head with the latest block
                latest_hash = self.find_latest_block_hash()
                if latest_hash:
                    self.current_chain_head = latest_hash
                    self.logger.info(f"Updated chain head to {latest_hash[:16]}")
                
            # Handle pending fork resolution if needed
            if payload.request_hash in self.pending_sync_requests:
                fork_data = self.pending_sync_requests.pop(payload.request_hash)
                # Re-trigger fork resolution with the new blocks
                await self.resolve_fork_with_retry(fork_data)
                    
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding blocks data: {e}")
        except Exception as e:
            self.logger.error(f"Error processing sync response: {e}")
    
    @lazy_wrapper(MoveData)
    def on_move(self, peer: Peer, payload: MoveData) -> None:
        """Handle incoming move messages."""
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



    @lazy_wrapper(ProposerAnnouncement)
    async def on_proposer_announcement(self, peer: Peer, payload: ProposerAnnouncement) -> None:
        """Handles incoming proposer announcements."""
        print(f"Received ProposerAnnouncement for round {payload.round_seed_hex[:8]} from {payload.proposer_pubkey_hex[:8]} (peer {peer.mid.hex()[:8] if peer else 'Unknown Peer'})")

    @lazy_wrapper(ProposedBlockPayload)
    async def on_proposed_block(self, peer: Peer, payload: ProposedBlockPayload) -> None:

        # Check if there's a fork and try to resolve it
        if payload.previous_block_hash != self.get_latest_block_hash():
            fork_resolved = await self.resolve_fork_with_retry(payload)
            if not fork_resolved:
                self.logger.warning(f"Previous block hash mismatch. Expected {self.get_latest_block_hash()[:16]}, got {payload.previous_block_hash[:16]}. Attempting to sync blocks...")
                return
            else:
                self.logger.info(f"Fork successfully resolved!")
        
        """Handles an incoming proposed block with full validation."""
        self.logger.info(f"Received ProposedBlockPayload for round {payload.round_seed_hex[:8]} from peer {peer.mid.hex()[:8] if peer else 'Unknown Peer'} (claimed proposer: {payload.proposer_pubkey_hex[:8]})")

        try:
            proposer_public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.proposer_pubkey_hex))
            
            # Update signature verification to include timestamp and previous block hash
            block_data_to_verify_str = f"{payload.round_seed_hex}:{payload.merkle_root}:{payload.proposer_pubkey_hex}:{payload.previous_block_hash}:{payload.timestamp}"
            block_data_to_verify_bytes = block_data_to_verify_str.encode('utf-8')
            block_signature_bytes = bytes.fromhex(payload.signature)
            
            proposer_public_key.verify(block_signature_bytes, block_data_to_verify_bytes)
            self.logger.info(f"Block signature VERIFIED for block by {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]}.")
                
            # Verify previous block hash is valid
            latest_block_hash = self.get_latest_block_hash()
            if payload.previous_block_hash != latest_block_hash:
                self.logger.warning(f"Previous block hash mismatch. Expected {latest_block_hash}, got {payload.previous_block_hash}. Discarding.")
                return
            
        except InvalidSignature:
            self.logger.warning(f"Block signature INVALID for block by {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]}. Discarding block.")
            return
        except Exception as e:
            self.logger.error(f"Error during block signature verification for block by {payload.proposer_pubkey_hex[:8]}: {e}. Discarding block.")
            return

        if not payload.transaction_hashes:
            if payload.merkle_root != MerkleTree([]).get_root():
                self.logger.warning(f"Block from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} has no transaction hashes, but Merkle root {payload.merkle_root} does not match expected empty root. Discarding.")
                return
            self.logger.info(f"Block from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} is an empty block and Merkle root is consistent.")
        else:
            try:
                reconstructed_merkle_tree = MerkleTree(payload.transaction_hashes)
                reconstructed_merkle_root = reconstructed_merkle_tree.get_root()
                if reconstructed_merkle_root == payload.merkle_root:
                    self.logger.info(f"Merkle root VERIFIED for block by {payload.proposer_pubkey_hex[:8]} (found {len(payload.transaction_hashes)} tx_hashes). Root: {payload.merkle_root}")
                else:
                    self.logger.warning(f"Merkle root INVALID for block by {payload.proposer_pubkey_hex[:8]}. Expected {payload.merkle_root}, got {reconstructed_merkle_root}. Discarding block.")
                    return
            except Exception as e:
                self.logger.error(f"Error during Merkle root verification for block by {payload.proposer_pubkey_hex[:8]}: {e}. Discarding block.")
                return
                
        self.logger.info(f"Block from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} PASSED all verifications.")
        
        # If the block passes all verification checks, create and send a vote
        # Only vote if we meet the stake requirement
        if self.stakes[self.pubkey_bytes] >= self.MIN_STAKE:
            await self.send_validator_vote(payload)
        else:
            self.logger.info(f"Not voting on block from {payload.proposer_pubkey_hex[:8]} for round {payload.round_seed_hex[:8]} due to insufficient stake.")


    @lazy_wrapper(ChessTransaction)
    def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
        """Handle incoming transactions with verification and storage using default_serializer."""
        try:
            proposer_pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.proposer_pubkey_hex))
            tx_data_to_verify = f"{payload.match_id}:{payload.winner}:{payload.nonce}:{payload.proposer_pubkey_hex}".encode()
            proposer_pubkey.verify(bytes.fromhex(payload.signature), tx_data_to_verify)
            self.logger.info(f"Transaction {payload.nonce} signature verified successfully.")
        except InvalidSignature:
            self.logger.warning(f"Transaction {payload.nonce} from {peer.mid.hex()[:8] if peer else 'Unknown Peer'} failed signature verification. Discarding.")
            return
        except Exception as e:
            self.logger.error(f"Error during signature verification for transaction {payload.nonce}: {e}. Discarding.")
            return

        if payload.nonce in self.mempool or self.is_transaction_in_db(payload.nonce):
            self.logger.info(f"Transaction {payload.nonce} already processed or in mempool. Skipping.")
            return

        self.mempool[payload.nonce] = payload 
        self.logger.info(f"Transaction {payload.nonce} added to mempool. Mempool size: {len(self.mempool)}")

        try:
            packed_tx = default_serializer.pack_serializable(payload)
            with self.db_env.begin(write=True) as txn:
                tx_db = self.db_env.open_db(b'transactions', txn=txn, create=True)
                txn.put(payload.nonce.encode('utf-8'), packed_tx, db=tx_db)
            self.logger.info(f"Accepted and stored transaction {payload.nonce} from {peer.mid.hex()[:8] if peer else 'Unknown Peer'}")
        except Exception as e:
            self.logger.error(f"Failed to store transaction {payload.nonce} in DB: {e}")
            if payload.nonce in self.mempool:
                del self.mempool[payload.nonce]


    def initialize_blockchain(self) -> None:
        """Initialize the blockchain with a genesis block if none exists."""
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        
        # Check if we already have blocks
        with self.db_env.begin(db=blocks_db) as txn:
            cursor = txn.cursor()
            if cursor.first():  # If there's at least one block
                self.logger.info("Blockchain already initialized with existing blocks")
                return
        
        # Create genesis block with special parameters
        genesis_seed = "0000000000000000000000000000000000000000000000000000000000000000"
        genesis_time = 1714501200
        
        # Create a dummy genesis transaction hash
        genesis_tx_hash = hashlib.sha256(f"genesis_tx_{genesis_time}".encode()).hexdigest()

        # Calculate Merkle root for the genesis transaction
        merkle_tree_genesis = MerkleTree([genesis_tx_hash])
        genesis_merkle_root = merkle_tree_genesis.get_root()
        if not genesis_merkle_root:
            self.logger.error("Failed to generate Merkle root for genesis block. Using a fallback.")
            genesis_merkle_root = hashlib.sha256("fallback_genesis_root_error".encode()).hexdigest()

        # For genesis block, use all zeros as previous hash
        previous_block_hash = "0" * 64  # 64 hex characters = 32 bytes

        # Sign the genesis block with our key - use the same format as regular blocks
        genesis_data_to_sign = f"{genesis_seed}:{genesis_merkle_root}:{self.pubkey_bytes.hex()}:{previous_block_hash}:{genesis_time}"
        genesis_signature = self.sk.sign(genesis_data_to_sign.encode('utf-8')).hex()

        # Create the genesis block payload
        genesis_block = ProposedBlockPayload.create(
            round_seed_hex=genesis_seed,
            transaction_hashes=[genesis_tx_hash],
            merkle_root=genesis_merkle_root,
            proposer_pubkey_hex=self.pubkey_bytes.hex(),
            signature=genesis_signature,
            previous_block_hash=previous_block_hash,
            timestamp=genesis_time
        )

        # Calculate block hash using the SAME format as in add_confirmed_block()
        genesis_block_hash = hashlib.sha256(genesis_data_to_sign.encode('utf-8')).hexdigest()
        
        with self.db_env.begin(db=blocks_db, write=True) as txn:
            # Convert the transaction_hashes list to a string before serialization
            tx_hashes_str = ",".join(genesis_block.transaction_hashes)
            
            modified_block = ProposedBlockPayload(
                round_seed_hex=genesis_block.round_seed_hex,
                transaction_hashes_str=tx_hashes_str,
                merkle_root=genesis_block.merkle_root,
                proposer_pubkey_hex=genesis_block.proposer_pubkey_hex,
                signature=genesis_block.signature,
                previous_block_hash=previous_block_hash,
                timestamp=genesis_block.timestamp
            )
            
            serialized_genesis = default_serializer.pack_serializable(modified_block)
            txn.put(genesis_block_hash.encode('utf-8'), serialized_genesis)

        self.logger.info(f"Initialized blockchain with genesis block {genesis_block_hash[:16]}")
        self.logger.info(f"Genesis block created with seed {genesis_seed} and Merkle root {genesis_merkle_root[:16]}")    
        # Create a dummy genesis transaction and store it in the database
        try:
            # The nonce of the genesis transaction is its hash, used in the Merkle tree
            genesis_tx = ChessTransaction(
                match_id="genesis_match",
                winner="genesis",
                moves_hash="genesis_moves", # Placeholder, as no actual moves for genesis tx
                nonce=genesis_tx_hash, 
                proposer_pubkey_hex=self.pubkey_bytes.hex(),
                # Signature for the transaction itself
                signature=self.sk.sign(f"genesis_match:genesis:{genesis_tx_hash}".encode()).hex()
            )
            
            with self.db_env.begin(db=self.tx_db, write=True) as txn:
                serialized_tx = default_serializer.pack_serializable(genesis_tx)
                txn.put(genesis_tx_hash.encode(), serialized_tx)
                
            # Mark this transaction as processed immediately
            processed_db = self.db_env.open_db(b'processed_transactions', create=True)
            with self.db_env.begin(db=processed_db, write=True) as txn:
                txn.put(genesis_tx_hash.encode(), b'1')
                
            self.transactions.add(genesis_tx_hash)
            self.logger.info(f"Created and stored genesis transaction with hash {genesis_tx_hash[:16]}")
            
            # Create additional dummy transactions for initial blocks
            self.create_dummy_transactions(3)  # Create 3 dummy transactions
            
        except Exception as e:
            self.logger.error(f"Failed to create genesis transaction: {e}")
    
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
        

    def checking_proposer(self, seed: bytes) -> bool:
        """Check if this peer is the proposer for the current round.
        
        Args:
            seed: The round seed
        
        Returns:
            bool: True if this peer is the proposer, False otherwise
        """
        # Get list of peer IDs for the lottery
        peer_ids = []
        for peer in self.get_peers():
            if peer.mid != self.pubkey_bytes:  # Don't include self twice
                peer_ids.append(peer.mid.hex())
        
        # Include self in the peer list
        peer_ids.append(self.pubkey_bytes.hex())
        
        # Call the lottery selection function with appropriate parameters
        is_proposer = lottery_selection(
            seed=seed,
            p_id=self.pubkey_bytes,
            total_stake=self.total_stake(),
            peers=peer_ids
        )
        
        if is_proposer:
            self.logger.info(f"I am the proposer for round with seed {seed.hex()[:8]}")
        else:
            self.logger.info(f"I am NOT the proposer for round with seed {seed.hex()[:8]}")
        
        return is_proposer

    def started(self) -> None:
        """Called when the community is started."""
        self.network.add_peer_observer(self)
        create_task(self.periodic_broadcast())
        create_task(self.startup_sequence())
    
    async def startup_sequence(self) -> None:
        """Handles the node startup sequence with proper synchronization."""
        self.logger.info("Node starting up. Beginning startup sequence...")
        
        # Wait for peer discovery (30 seconds)
        self.logger.info("Waiting for peer discovery (30 seconds)...")
        peer_discovery_time = 30
        start_time = time.time()
        
        while time.time() - start_time < peer_discovery_time:
            peers = self.get_peers()
            if peers:
                self.logger.info(f"Found {len(peers)} peers. Continuing startup sequence.")
                break
            await asyncio.sleep(2)  # Check every 2 seconds
        
        # Check if we found any peers
        peers = self.get_peers()
        if not peers:
            self.logger.warning("No peers found during discovery period. Will operate in standalone mode.")
        else:
            # Request blockchain data from peers
            self.logger.info(f"Beginning blockchain synchronization with {len(peers)} peers...")
            sync_success = await self.sync_blockchain_data()
            
            if sync_success:
                self.logger.info("Blockchain synchronization completed successfully.")
            else:
                self.logger.warning("Blockchain synchronization incomplete or failed. Continuing with local state.")
        
        # Start PoS rounds only after synchronization attempt
        self.logger.info("Starting PoS consensus rounds...")
        create_task(self.pos_round())

    async def sync_blockchain_data(self) -> bool:
        """Synchronize blockchain data from peers.
        
        Returns:
            bool: True if synchronization was successful, False otherwise
        """
        # Track if we've successfully synced
        sync_complete = False
        sync_timeout = 60  # 1 minute timeout for initial sync
        
        # Request blockchain data from peers
        peers = self.get_peers()
        if not peers:
            return False
            
        # Create a synchronization request
        latest_hash = self.get_latest_block_hash()
        if not latest_hash:
            self.logger.info("No existing blocks found. Requesting complete blockchain.")
            request_hash = "0" * 64  # Request from genesis block
        else:
            self.logger.info(f"Latest known block: {latest_hash[:16]}. Requesting newer blocks.")
            request_hash = latest_hash
        
        # Send sync requests to peers
        sync_requests_sent = 0
        for peer in peers[:3]:  # Limit to 3 peers
            try:
                request = BlockSyncRequest(request_hash, count=100)
                self.ez_send(peer, request)
                sync_requests_sent += 1
                self.logger.info(f"Sent blockchain sync request to {peer.mid.hex()[:8]}")
            except Exception as e:
                self.logger.error(f"Error sending sync request to peer {peer.mid.hex()[:8]}: {e}")
        
        if sync_requests_sent == 0:
            return False
        
        # Wait for sync responses with timeout
        start_time = time.time()
        self.sync_responses_received = 0
        
        while time.time() - start_time < sync_timeout and self.sync_responses_received < sync_requests_sent:
            # Check if we've received responses in the on_block_sync_response handler
            if hasattr(self, 'sync_complete') and self.sync_complete:
                sync_complete = True
                break
            await asyncio.sleep(1)
        
        if sync_complete or self.sync_responses_received > 0:
            self.logger.info(f"Received {self.sync_responses_received} sync responses")
            return True
        else:
            self.logger.warning(f"Sync timeout reached after {sync_timeout} seconds with {self.sync_responses_received} responses")
            return False

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

        # Prepare data for signing the transaction
        # Use the community's Ed25519 public key
        proposer_pubkey_hex = self.pubkey_bytes.hex() 
        tx_data_to_sign = f"{match_id}:{winner}:{nonce}:{proposer_pubkey_hex}".encode()
        
        try:
            # Use the community's Ed25519 private key for signing
            transaction_signature_hex = self.sk.sign(tx_data_to_sign).hex()
        except Exception as e:
            self.logger.error(f"Error signing transaction data for match {match_id}, nonce {nonce}: {e}")
            return # Or handle error appropriately

        # Create and send the final transaction
        tx = ChessTransaction(
            match_id=match_id,
            winner=winner,
            moves_hash=",".join(str(m.id) for m in moves),  # Or a proper hash of moves
            nonce=nonce,
            proposer_pubkey_hex=proposer_pubkey_hex,
            signature=transaction_signature_hex # Pass signature at instantiation
        )

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
 
    def get_unprocessed_transactions(self) -> List[ChessTransaction]:
        """Get transactions from the database that haven't been included in a block yet."""
        out = []
        # Add a DB to track which transactions have been included in confirmed blocks
        processed_db = self.db_env.open_db(b'processed_transactions', create=True)
        
        with self.db_env.begin(db=self.tx_db) as txn:
            with self.db_env.begin(db=processed_db) as processed_txn:
                for key, raw in txn.cursor():
                    # Skip if this transaction has been processed
                    if processed_txn.get(key) is not None:
                        continue
                        
                    try:
                        deserialized_tx, _ = default_serializer.unpack_serializable(ChessTransaction, raw)
                        out.append(deserialized_tx)
                    except Exception as e:
                        key_repr = key.hex() if isinstance(key, bytes) else str(key)
                        print(f"Error loading transaction {key_repr}: {e}")
        return out
    
    def mark_transactions_as_processed(self, transaction_hashes: List[str]) -> None:
        """Mark transactions as processed after a block containing them is confirmed."""
        processed_db = self.db_env.open_db(b'processed_transactions', create=True)
        with self.db_env.begin(db=processed_db, write=True) as txn:
            for tx_hash in transaction_hashes:
                txn.put(tx_hash.encode(), b'1')
                
                # Remove from pending and mempool if present
                if tx_hash in self.pending_transactions:
                    del self.pending_transactions[tx_hash]
                if tx_hash in self.mempool:
                    del self.mempool[tx_hash]
    


    def reprocess_transactions(self, old_chain: List[str], new_chain: List[str]) -> None:
        """Re-process any transactions that might have been lost or need to be reverted
        when switching from one chain to another.
        
        Args:
            old_chain: The chain we're switching from
            new_chain: The chain we're switching to
        """
        self.logger.info(f"Reprocessing transactions when switching chains")
        
        # Find the common ancestor block
        common_ancestor = None
        old_blocks_set = set(old_chain)
        for block_hash in new_chain:
            if block_hash in old_blocks_set:
                common_ancestor = block_hash
                break
        
        if not common_ancestor:
            self.logger.warning("No common ancestor found between chains, cannot safely reprocess transactions")
            return
            
        # Collect transactions to revert (in old_chain after fork) and to apply (in new_chain after fork)
        transactions_to_revert = []
        transactions_to_apply = []
        
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        
        # Collect transactions in blocks that need to be reverted
        with self.db_env.begin(db=blocks_db) as txn:
            for block_hash in old_chain:
                if block_hash == common_ancestor:
                    break
                    
                block_data = txn.get(block_hash.encode('utf-8'))
                if block_data:
                    try:
                        block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                        transactions_to_revert.extend(block.transaction_hashes)
                    except Exception as e:
                        self.logger.error(f"Error unpacking block {block_hash[:16]} for reversion: {e}")
        
        # Collect transactions in blocks that need to be applied
        with self.db_env.begin(db=blocks_db) as txn:
            for block_hash in new_chain:
                if block_hash == common_ancestor:
                    break
                    
                block_data = txn.get(block_hash.encode('utf-8'))
                if block_data:
                    try:
                        block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                        transactions_to_apply.extend(block.transaction_hashes)
                    except Exception as e:
                        self.logger.error(f"Error unpacking block {block_hash[:16]} for application: {e}")
        
        self.logger.info(f"Reverting {len(transactions_to_revert)} transactions and applying {len(transactions_to_apply)} transactions")
        
        # Mark reverted transactions as unprocessed so they can be included in future blocks if valid
        processed_db = self.db_env.open_db(b'processed_transactions', create=True)
        with self.db_env.begin(db=processed_db, write=True) as txn:
            for tx_hash in transactions_to_revert:
                try:
                    txn.delete(tx_hash.encode())
                    # Re-add to mempool if it's still valid
                    with self.db_env.begin(db=self.tx_db) as tx_txn:
                        tx_data = tx_txn.get(tx_hash.encode())
                        if tx_data:
                            tx, _ = default_serializer.unpack_serializable(ChessTransaction, tx_data)
                            self.mempool[tx_hash] = tx
                except Exception as e:
                    self.logger.error(f"Error reverting transaction {tx_hash}: {e}")
        
        # Mark applied transactions as processed
        with self.db_env.begin(db=processed_db, write=True) as txn:
            for tx_hash in transactions_to_apply:
                try:
                    txn.put(tx_hash.encode(), b'1')
                    # Remove from mempool
                    if tx_hash in self.mempool:
                        del self.mempool[tx_hash]
                except Exception as e:
                    self.logger.error(f"Error applying transaction {tx_hash}: {e}")
                    
    def get_latest_block_hash(self) -> str:
        """Get the hash of the latest confirmed block in the blockchain."""
        # If we have a tracked current head, return it
        if self.current_chain_head:
            return self.current_chain_head
            
        # Otherwise fall back to database lookup
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        
        latest_hash = ""
        with self.db_env.begin(db=blocks_db) as txn:
            cursor = txn.cursor()
            # Position at last key
            if cursor.last():
                latest_hash = cursor.key().decode('utf-8')
        
        # Update our tracked head
        self.current_chain_head = latest_hash
        return latest_hash
    
    def select_propagation_peers(self, count: int = 5) -> List[Peer]:
        """Select a subset of peers for efficient gossip protocol propagation.
        
        Args:
            count: Maximum number of peers to select
            
        Returns:
            List[Peer]: Selected subset of peers
        """
        peers = self.get_peers()
        if not peers:
            return []
            
        # If we have fewer peers than requested, return all of them
        if len(peers) <= count:
            return peers
            
        # Otherwise, select a random subset using deterministic order based on peer IDs
        # This helps ensure more even distribution across the network
        sorted_peers = sorted(peers, key=lambda p: p.mid)
        peer_index = self.pos_round_number % len(sorted_peers)  # Cycle through the peers
        
        # Select count peers starting from peer_index, wrapping around if needed
        selected = []
        for i in range(count):
            idx = (peer_index + i) % len(sorted_peers)
            selected.append(sorted_peers[idx])
            
        return selected
    
    def store_proposed_block(self, block: ProposedBlockPayload) -> None:
        """Store a proposed block for consensus tracking.
        
        Args:
            block: The proposed block payload
        """
        # Create a database for proposed blocks if it doesn't exist
        proposed_blocks_db = self.db_env.open_db(b'proposed_blocks', create=True)
        
        # Block ID is a combination of round and proposer
        block_id = f"{block.round_seed_hex}:{block.proposer_pubkey_hex[:8]}".encode('utf-8')
        
        # Serialize and store the block
        serialized_block = default_serializer.pack_serializable(block)
        with self.db_env.begin(db=proposed_blocks_db, write=True) as txn:
            txn.put(block_id, serialized_block)
            
        self.logger.info(f"Stored proposed block with ID {block_id.decode('utf-8')}")
    
    def resolve_fork(self, proposed_block: ProposedBlockPayload) -> bool:
        """Attempt to resolve a blockchain fork.
        
        Args:
            proposed_block: The block that caused the fork detection
            
        Returns:
            bool: True if the fork was resolved, False if not
        """
        self.logger.warning("Fork detected! Attempting to resolve...")
        
        # Get the chain from the proposed block's previous hash
        alt_chain = self.get_chain_from_hash(proposed_block.previous_block_hash)
        
        if not alt_chain:
            self.logger.warning(f"Unable to find alternative chain for previous hash {proposed_block.previous_block_hash[:16]}")
            return False
        
        # Get our current chain
        my_chain = self.get_chain_from_hash(self.get_latest_block_hash())
        
        # Compare chain lengths (simple longest chain wins rule)
        if len(alt_chain) > len(my_chain):
            self.logger.info(f"Alternative chain is longer ({len(alt_chain)} > {len(my_chain)}). Switching to it.")
            
            # Re-process any transactions that might have been lost
            self.reprocess_transactions(my_chain, alt_chain)
            
            # Update our chain pointer
            self.current_chain_head = proposed_block.previous_block_hash
            
            # Important: Log the change for debugging
            self.logger.info(f"Chain head updated to {self.current_chain_head[:16]}")
            return True
        else:
            self.logger.info(f"Our chain is longer or equal ({len(my_chain)} >= {len(alt_chain)}). Keeping it.")
            return False

    def get_chain_from_hash(self, start_hash: str, max_blocks: int = 100) -> List[str]:
        """Get chain of blocks starting from a specific hash.
        
        Args:
            start_hash: Hash to start from
            max_blocks: Maximum blocks to retrieve
            
        Returns:
            List of block hashes in the chain
        """
        chain = []
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        
        current_hash = start_hash
        
        with self.db_env.begin(db=blocks_db) as txn:
            while current_hash and len(chain) < max_blocks:
                block_data = txn.get(current_hash.encode('utf-8'))
                if not block_data:
                    break
                    
                chain.append(current_hash)
                
                try:
                    block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                    current_hash = block.previous_block_hash
                    
                    # Stop at genesis block
                    if current_hash == "0" * 64:
                        chain.append(current_hash)
                        break
                except Exception as e:
                    self.logger.error(f"Error deserializing block: {e}")
                    break
                    
        return chain

    async def pos_round(self) -> None:
        """Perform a round of PoS block proposal."""
        while True:
            self.pos_round_number += 1
            current_time = time.time()
            self.logger.info(f"Starting PoS round {self.pos_round_number} at {current_time}")

            # Generate a round seed based on the current time
            seed = hashlib.sha256(str(self.pos_round_number).encode()).digest()

            # check if mystake is more than MIN_STAKE
            if self.stakes[self.pubkey_bytes] < self.MIN_STAKE:
                print(f"Stake too low ({self.stakes[self.pubkey_bytes]}), not proposing")
                await sleep(self.POS_ROUND_INTERVAL)
                continue
            
            # check if we are the proposer
            proposer = self.checking_proposer(seed)
            if proposer:
                # Announce to the network
                for p in self.get_peers():
                    if p.mid != self.pubkey_bytes:
                        announcement = ProposerAnnouncement(
                            round_seed_hex=seed.hex(),
                            proposer_pubkey_hex=self.pubkey_bytes.hex(),
                        )
                        serialized = default_serializer.pack_serializable(announcement)
                        self.logger.debug(f"Sending announcement: {len(serialized)} bytes, fields: {seed.hex()[:8]}, {self.pubkey_bytes.hex()[:8]}")
                        self.ez_send(p, announcement)
                self.logger.info(f"Announced proposer for round {seed.hex()[:8]}: {self.pubkey_bytes.hex()[:8]}")

                # Fetch only unprocessed transactions from storage
                transactions_to_propose: List[ChessTransaction] = []
                processed_nonces = set()

                # Fetch only recent/unprocessed transactions instead of all transactions
                stored_transactions = self.get_unprocessed_transactions()
                
                for tx in stored_transactions:
                    if tx.nonce not in processed_nonces:
                        transactions_to_propose.append(tx)
                        processed_nonces.add(tx.nonce)
                
                self.logger.info(f"Round {self.pos_round_number}: Fetched {len(transactions_to_propose)} unprocessed transactions from DB.")

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
                    continue

                # Construct Merkle tree from transaction nonces
                transaction_hashes = [tx.nonce for tx in transactions_to_propose]
                if not transaction_hashes:
                    self.logger.warning(f"Round {self.pos_round_number}: Transaction hashes list is empty despite having transactions. This should not happen.")
                    await sleep(self.POS_ROUND_INTERVAL)
                    continue

                merkle_tree = MerkleTree(transaction_hashes)
                merkle_root = merkle_tree.get_root()
                if not merkle_root:
                    self.logger.error(f"Round {self.pos_round_number}: Failed to generate Merkle root.")
                    await sleep(self.POS_ROUND_INTERVAL)
                    continue

                self.logger.info(f"Round {self.pos_round_number}: Merkle root for {len(transaction_hashes)} transactions: {merkle_root}")

                # Create the proposed block payload
                round_seed_hex = seed.hex()
                proposer_pubkey_hex = self.pubkey_bytes.hex()
                previous_block_hash = self.get_latest_block_hash()
                block_timestamp = int(time.time())

                # Include timestamp and previous block hash in the signed data
                block_data_to_sign_str = f"{round_seed_hex}:{merkle_root}:{proposer_pubkey_hex}:{previous_block_hash}:{block_timestamp}"
                block_data_to_sign_bytes = block_data_to_sign_str.encode('utf-8')
                
                try:
                    signature_hex = self.sk.sign(block_data_to_sign_bytes).hex()
                except Exception as e:
                    self.logger.error(f"Round {self.pos_round_number}: Error signing block data: {e}")
                    await sleep(self.POS_ROUND_INTERVAL)
                    continue

                try:
                    proposed_block = ProposedBlockPayload(
                        round_seed_hex=round_seed_hex,
                        transaction_hashes_str=",".join(transaction_hashes),  # Changed from transaction_hashes=transaction_hashes
                        merkle_root=merkle_root,
                        proposer_pubkey_hex=proposer_pubkey_hex,
                        signature=signature_hex,
                        timestamp=block_timestamp,  # Add timestamp for block ordering
                        previous_block_hash=previous_block_hash  # Add reference to previous block
                    )

                    self.logger.info(f"Round {self.pos_round_number}: Proposing block with Merkle root {merkle_root}, timestamp {block_timestamp}, and {len(transaction_hashes)} transactions.")
                    
                    # Implement more efficient propagation using gossip protocol
                    # Select a subset of peers to reduce network congestion
                    selected_peers = self.select_propagation_peers(5)  # Select 5 peers initially
                    if selected_peers:
                        for peer in selected_peers:
                            try:
                                self.ez_send(peer, proposed_block)
                                self.logger.debug(f"Round {self.pos_round_number}: Sent block proposal to peer {peer.mid.hex()[:8]}")
                            except Exception as e:
                                self.logger.warning(f"Round {self.pos_round_number}: Failed to send block to peer {peer.mid.hex()[:8]}: {e}")
                        
                        # Mark transactions as pending instead of deleting them
                        pending_count = 0
                        for tx_nonce in transaction_hashes:
                            if tx_nonce in self.mempool:
                                # Move to pending state rather than deleting
                                self.pending_transactions[tx_nonce] = self.mempool[tx_nonce]
                                pending_count += 1
                        
                        # Store the proposed block for consensus tracking
                        self.store_proposed_block(proposed_block)
                        
                        self.logger.info(f"Round {self.pos_round_number}: Marked {pending_count} proposed transactions as pending confirmation.")
                    else:
                        self.logger.warning(f"Round {self.pos_round_number}: No peers available for block propagation")
                        
                except Exception as e:
                    self.logger.error(f"Round {self.pos_round_number}: Error creating or sending proposed block: {e}")
            else:
                self.logger.info(f"Waiting to be selected as validator for round {self.pos_round_number} with seed {seed.hex()[:8]}")   
                # If not selected, just wait for the next round


                # if we are validator, we will be notified by the network
                # here goes the logic of validator
            # Always continue the loop, don't return
            await sleep(self.POS_ROUND_INTERVAL)
    
    async def send_validator_vote(self, block: ProposedBlockPayload) -> None:
        """Send a validator vote for a proposed block.
        
        Args:
            block: The proposed block to vote on
        """
        from models.models import ValidatorVote
        
        # Create a unique block identifier
        block_id = f"{block.round_seed_hex}:{block.merkle_root}"
        
        # Check if we've already voted on this block
        if block_id in self.processed_blocks:
            self.logger.info(f"Already processed block {block_id[:16]}. Skipping vote.")
            return
        
        # Create vote data to sign (include all relevant block data for security)
        vote_data = f"{block.round_seed_hex}:{block.merkle_root}:{block.proposer_pubkey_hex}:{self.pubkey_bytes.hex()}:true"
        vote_signature = self.sk.sign(vote_data.encode('utf-8')).hex()
        
        # Create the vote payload
        vote = ValidatorVote(
            round_seed_hex=block.round_seed_hex,
            block_merkle_root=block.merkle_root,
            proposer_pubkey_hex=block.proposer_pubkey_hex,
            validator_pubkey_hex=self.pubkey_bytes.hex(),
            vote=True,  # True means approval
            signature=vote_signature
        )
        
        # Initialize vote tracking for this block if needed
        if block_id not in self.block_votes:
            self.block_votes[block_id] = {}
        
        # Register our own vote
        self.block_votes[block_id][self.pubkey_bytes.hex()] = True
        
        # Send the vote to peers using efficient gossip protocol
        selected_peers = self.select_propagation_peers(3)  # Use fewer peers for votes
        if selected_peers:
            for peer in selected_peers:
                try:
                    self.ez_send(peer, vote)
                    self.logger.debug(f"Sent vote for block {block_id[:16]} to {peer.mid.hex()[:8]}")
                except Exception as e:
                    self.logger.warning(f"Failed to send vote to {peer.mid.hex()[:8]}: {e}")
        
        # Mark this block as processed
        self.processed_blocks.add(block_id)
        
        # Check if we have enough votes for consensus
        await self.check_consensus(block)
    
    async def on_validator_vote(self, peer: Peer, payload) -> None:
        """Handle incoming validator votes."""
        from models.models import ValidatorVote
        
        # Type checking since we're manually receiving this as a parameter
        if not isinstance(payload, ValidatorVote):
            self.logger.error(f"Received incorrect payload type for validator vote: {type(payload)}")
            return
        
        block_id = f"{payload.round_seed_hex}:{payload.block_merkle_root}"
        self.logger.info(f"Received validator vote for block {block_id[:16]} from {payload.validator_pubkey_hex[:8]}")
        
        # Verify the vote signature
        try:
            validator_pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.validator_pubkey_hex))
            vote_data = f"{payload.round_seed_hex}:{payload.block_merkle_root}:{payload.proposer_pubkey_hex}:{payload.validator_pubkey_hex}:{'true' if payload.vote else 'false'}"
            validator_pubkey.verify(bytes.fromhex(payload.signature), vote_data.encode('utf-8'))
        except Exception as e:
            self.logger.warning(f"Invalid vote signature from {payload.validator_pubkey_hex[:8]}: {e}")
            return
        
        # Initialize vote tracking for this block if needed
        if block_id not in self.block_votes:
            self.block_votes[block_id] = {}
        
        # Record this vote
        self.block_votes[block_id][payload.validator_pubkey_hex] = payload.vote
        
        # Forward this vote to other peers for gossip propagation
        if block_id not in self.processed_blocks:
            selected_peers = self.select_propagation_peers(2)  # Use fewer peers for forwarding votes
            if selected_peers:
                for forward_peer in selected_peers:
                    if forward_peer.mid.hex() != peer.mid.hex():  # Don't send back to sender
                        try:
                            self.ez_send(forward_peer, payload)
                            self.logger.debug(f"Forwarded vote for block {block_id[:16]} to {forward_peer.mid.hex()[:8]}")
                        except Exception as e:
                            self.logger.warning(f"Failed to forward vote to {forward_peer.mid.hex()[:8]}: {e}")
        
        # If we're the block proposer, check for consensus
        if payload.proposer_pubkey_hex == self.pubkey_bytes.hex():
            # Get the block from our stored proposals
            proposed_blocks_db = self.db_env.open_db(b'proposed_blocks', create=True)
            proposed_block = None
            
            try:
                with self.db_env.begin(db=proposed_blocks_db) as txn:
                    for key, data in txn.cursor():
                        key_str = key.decode('utf-8')
                        if key_str.startswith(f"{payload.round_seed_hex}:"):
                            proposed_block_data, _ = default_serializer.unpack_serializable(ProposedBlockPayload, data)
                            if proposed_block_data.merkle_root == payload.block_merkle_root:
                                proposed_block = proposed_block_data
                                break
                
                if proposed_block:
                    await self.check_consensus(proposed_block)
                else:
                    self.logger.warning(f"Received vote for unknown block {block_id[:16]}")
            except Exception as e:
                self.logger.error(f"Error retrieving proposed block for vote check: {e}")
    
    async def check_consensus(self, block: ProposedBlockPayload) -> None:
        """Check if consensus has been reached for a block.
        
        Args:
            block: The proposed block to check consensus for
        """
        from models.models import BlockConfirmation
        
        block_id = f"{block.round_seed_hex}:{block.merkle_root}"
        
        # Skip if we've already confirmed this block
        if block_id in self.block_confirmations:
            return
            
        # Get votes for this block
        if block_id not in self.block_votes:
            return
            
        votes = self.block_votes[block_id]
        
        # Count positive votes (weighted by stake)
        total_stake = 0
        approving_stake = 0
        
        for voter_pubkey, vote in votes.items():
            try:
                voter_stake = self.stakes.get(bytes.fromhex(voter_pubkey), 0)
                total_stake += voter_stake
                if vote:  # True means approval
                    approving_stake += voter_stake
            except Exception as e:
                self.logger.warning(f"Error counting stake for voter {voter_pubkey[:8]}: {e}")
        
        # Check if quorum threshold is met
        if total_stake > 0 and approving_stake / total_stake >= self.QUORUM_RATIO:
            self.logger.info(f"Consensus reached for block {block_id[:16]} with {approving_stake}/{total_stake} stake ({approving_stake/total_stake:.2f})")
            
            # Create block confirmation
            confirmation_data = f"{block.round_seed_hex}:{block.merkle_root}:{block.proposer_pubkey_hex}:{block.timestamp}:{len(votes)}"
            confirmation_signature = self.sk.sign(confirmation_data.encode('utf-8')).hex()
            
            confirmation = BlockConfirmation(
                round_seed_hex=block.round_seed_hex,
                block_merkle_root=block.merkle_root,
                proposer_pubkey_hex=block.proposer_pubkey_hex,
                timestamp=block.timestamp,
                signatures_count=len(votes),
                confirmer_pubkey_hex=self.pubkey_bytes.hex(),
                signature=confirmation_signature
            )
            
            # Store the confirmation
            self.block_confirmations[block_id] = confirmation
            
            # Broadcast confirmation to network
            for peer in self.get_peers():
                try:
                    self.ez_send(peer, confirmation)
                except Exception as e:
                    self.logger.warning(f"Failed to send confirmation to {peer.mid.hex()[:8]}: {e}")
            
            # Add the confirmed block to the blockchain
            await self.add_confirmed_block(block)
        else:
            self.logger.info(f"Not enough votes for block {block_id[:16]} yet: {approving_stake}/{total_stake} stake ({approving_stake/total_stake:.2f} vs required {self.QUORUM_RATIO})")
    
    async def on_block_confirmation(self, peer: Peer, payload) -> None:
        """Handle incoming block confirmations."""
        from models.models import BlockConfirmation
        
        # Type checking
        if not isinstance(payload, BlockConfirmation):
            self.logger.error(f"Received incorrect payload type for block confirmation: {type(payload)}")
            return
            
        block_id = f"{payload.round_seed_hex}:{payload.block_merkle_root}"
        self.logger.info(f"Received block confirmation for {block_id[:16]} from {payload.confirmer_pubkey_hex[:8]} with {payload.signatures_count} signatures")
        
        # Verify the confirmation signature
        try:
            confirmer_pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.confirmer_pubkey_hex))
            confirmation_data = f"{payload.round_seed_hex}:{payload.block_merkle_root}:{payload.proposer_pubkey_hex}:{payload.timestamp}:{payload.signatures_count}"
            confirmer_pubkey.verify(bytes.fromhex(payload.signature), confirmation_data.encode('utf-8'))
        except Exception as e:
            self.logger.warning(f"Invalid confirmation signature from {payload.confirmer_pubkey_hex[:8]}: {e}")
            return
        
        # Store this confirmation if we haven't already
        if block_id not in self.block_confirmations:
            self.block_confirmations[block_id] = payload
            
            # Forward to more peers for gossip propagation
            selected_peers = self.select_propagation_peers(3)
            if selected_peers:
                for forward_peer in selected_peers:
                    if forward_peer.mid.hex() != peer.mid.hex():  # Don't send back to sender
                        try:
                            self.ez_send(forward_peer, payload)
                        except Exception as e:
                            self.logger.warning(f"Failed to forward confirmation to {forward_peer.mid.hex()[:8]}: {e}")
            
            # Find the proposed block data and add to blockchain
            proposed_blocks_db = self.db_env.open_db(b'proposed_blocks', create=True)
            try:
                with self.db_env.begin(db=proposed_blocks_db) as txn:
                    for key, data in txn.cursor():
                        key_str = key.decode('utf-8')
                        if key_str.startswith(f"{payload.round_seed_hex}:"):
                            proposed_block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, data)
                            if proposed_block.merkle_root == payload.block_merkle_root:
                                await self.add_confirmed_block(proposed_block)
                                return
                self.logger.warning(f"Received confirmation for unknown block {block_id[:16]}")
            except Exception as e:
                self.logger.error(f"Error retrieving proposed block for confirmation: {e}")
    
    async def add_confirmed_block(self, block: ProposedBlockPayload) -> None:
        """Add a confirmed block to the blockchain and update state accordingly.
        
        Args:
            block: The confirmed block to add to the chain
        """
        # Create a database for the confirmed blockchain if it doesn't exist
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        
        # Calculate the block hash for the key
        block_data_str = f"{block.round_seed_hex}:{block.merkle_root}:{block.proposer_pubkey_hex}:{block.previous_block_hash}:{block.timestamp}"
        block_hash = hashlib.sha256(block_data_str.encode('utf-8')).hexdigest()
        
        try:
            # Serialize and store the confirmed block
            serialized_block = default_serializer.pack_serializable(block)
            with self.db_env.begin(db=blocks_db, write=True) as txn:
                txn.put(block_hash.encode('utf-8'), serialized_block)
                
            self.logger.info(f"Added confirmed block {block_hash[:16]} to blockchain with {len(block.transaction_hashes)} transactions")
            
            # Update transaction status, remove from mempool and pending
            self.mark_transactions_as_processed(block.transaction_hashes)
            
            # Reward the proposer
            await self.reward_proposer(block.proposer_pubkey_hex)
            
        except Exception as e:
            self.logger.error(f"Failed to add confirmed block to blockchain: {e}")
    
    async def reward_proposer(self, proposer_pubkey_hex: str) -> None:
        """Reward the proposer of a confirmed block with additional stake.
        
        Args:
            proposer_pubkey_hex: The hex-encoded public key of the proposer
        """
        try:
            # Convert hex pubkey to bytes
            proposer_pubkey_bytes = bytes.fromhex(proposer_pubkey_hex)
            
            # Award a small stake reward (adjust based on economic model)
            reward_amount = 2
            
            # Update stake in memory and database
            current_stake = self.stakes.get(proposer_pubkey_bytes, 0)
            new_stake = current_stake + reward_amount
            
            with self.db_env.begin(db=self.stake_db, write=True) as txn:
                txn.put(proposer_pubkey_bytes, str(new_stake).encode('utf-8'))
                
            self.stakes[proposer_pubkey_bytes] = new_stake
            
            if proposer_pubkey_hex == self.pubkey_bytes.hex():
                self.logger.info(f"Received block proposal reward of {reward_amount} stake. New total: {new_stake}")
            else:
                self.logger.info(f"Awarded block proposal reward of {reward_amount} stake to {proposer_pubkey_hex[:8]}. Their new total: {new_stake}")
                
        except Exception as e:
            self.logger.error(f"Failed to reward proposer {proposer_pubkey_hex[:8]}: {e}")