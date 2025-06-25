import hashlib
import json
import time
from typing import Dict, List, Set
from logging import Logger
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
import lmdb
import asyncio
from ipv8.messaging.serialization import default_serializer
from ipv8.types import Peer
from models.models import ChessTransaction, ProposedBlockPayload, ProposerAnnouncement, ValidatorVote, BlockConfirmation, BlockSyncRequest, BlockSyncResponse
from utils.utils import lottery_selection
from utils.merkle import MerkleTree

class ConsensusManager:
    """Manages PoS consensus and blockchain operations for the chess community."""
    
    MAX_BLOCK_AGE = 3600
    SYNC_TIMEOUT = 60
    QUORUM_RATIO = 0.67
    POS_ROUND_INTERVAL = 20
    MIN_STAKE = 10
    GENESIS_PUBKEY_HEX = "..."
    GENESIS_SIGNATURE = "..."
    GENESIS_TIME = 1714501200
    GENESIS_SEED = "000000..."
    
    def __init__(self, community: 'ChessCommunity', data_manager: 'DataManager', logger: Logger) -> None:
        """Initialize the consensus manager."""
        self.logger = logger
        self.community = community
        self.data_manager = data_manager
        self.db_env = self.data_manager.db_env
        self.pos_round_number = 0
        self.current_chain_head = None
        self.round_proposers: Dict[str, str] = {}
        self.block_votes: Dict[str, Dict[str, bool]] = {}
        self.block_confirmations: Dict[str, BlockConfirmation] = {}
        self.processed_blocks: Set[str] = set()
        self.pending_sync_requests: Dict[str, ProposedBlockPayload] = {}
        self.sync_responses_received = 0
        self.initialize_blockchain()
    
    def initialize_blockchain(self) -> None:
        """Initialize the blockchain with a genesis block."""
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        with self.db_env.begin(db=blocks_db) as txn:
            cursor = txn.cursor()
            if cursor.first():
                self.logger.info("Blockchain already initialized with existing blocks")
                return
        
        genesis_tx_hash = hashlib.sha256(f"genesis_tx_{self.GENESIS_TIME}".encode()).hexdigest()
        merkle_tree = MerkleTree([genesis_tx_hash])
        genesis_merkle_root = merkle_tree.get_root()
        previous_block_hash = "0" * 64
        genesis_block = ProposedBlockPayload(
            round_seed_hex=self.GENESIS_SEED,
            transaction_hashes_str=genesis_tx_hash,
            merkle_root=genesis_merkle_root,
            proposer_pubkey_hex=self.GENESIS_PUBKEY_HEX,
            signature=self.GENESIS_SIGNATURE,
            previous_block_hash=previous_block_hash,
            timestamp=self.GENESIS_TIME
        )
        genesis_data_to_sign = f"{self.GENESIS_SEED}:{genesis_merkle_root}:{self.GENESIS_PUBKEY_HEX}:{previous_block_hash}:{self.GENESIS_TIME}"
        genesis_block_hash = hashlib.sha256(genesis_data_to_sign.encode('utf-8')).hexdigest()
        
        with self.db_env.begin(db=blocks_db, write=True) as txn:
            serialized_genesis = default_serializer.pack_serializable(genesis_block)
            txn.put(genesis_block_hash.encode('utf-8'), serialized_genesis)
        
        self.logger.info(f"Initialized blockchain with genesis block {genesis_block_hash[:16]}")
        try:
            genesis_tx = ChessTransaction(
                match_id="genesis_match",
                winner="genesis",
                moves_hash="genesis_moves",
                nonce=genesis_tx_hash,
                proposer_pubkey_hex=self.data_manager.pubkey_bytes.hex(),
                signature=self.data_manager.sk.sign(f"genesis_match:genesis:{genesis_tx_hash}".encode()).hex()
            )
            with self.db_env.begin(db=self.data_manager.tx_db, write=True) as txn:
                serialized_tx = default_serializer.pack_serializable(genesis_tx)
                txn.put(genesis_tx_hash.encode(), serialized_tx)
            with self.db_env.begin(db=self.data_manager.processed_db, write=True) as txn:
                txn.put(genesis_tx_hash.encode(), b'1')
            self.data_manager.transactions.add(genesis_tx_hash)
            self.logger.info(f"Created genesis transaction {genesis_tx_hash[:16]}")
            self.data_manager.create_dummy_transactions(3)
        except Exception as e:
            self.logger.error(f"Failed to create genesis transaction: {e}")
    
    async def pos_round(self) -> None:
        """Perform a PoS round."""
        while True:
            self.pos_round_number += 1
            current_time = time.time()
            self.logger.info(f"Starting PoS round {self.pos_round_number} at {current_time}")
            seed = hashlib.sha256(str(self.pos_round_number).encode()).digest()
            
            if self.data_manager.stakes[self.data_manager.pubkey_bytes] < self.MIN_STAKE:
                self.logger.info(f"Stake too low ({self.data_manager.stakes[self.data_manager.pubkey_bytes]}), not proposing")
                await asyncio.sleep(self.POS_ROUND_INTERVAL)
                continue
            
            peer_ids = [p.mid.hex() for p in self.community.get_peers() if p.mid != self.data_manager.pubkey_bytes]
            peer_ids.append(self.data_manager.pubkey_bytes.hex())
            is_proposer = lottery_selection(seed, self.data_manager.pubkey_bytes, self.data_manager.total_stake(), peer_ids)
            
            if is_proposer:
                self.logger.info(f"I am the proposer for round with seed {seed.hex()[:8]}")
                for p in self.community.get_peers():
                    if p.mid != self.data_manager.pubkey_bytes:
                        announcement = ProposerAnnouncement(
                            round_seed_hex=seed.hex(),
                            proposer_pubkey_hex=self.data_manager.pubkey_bytes.hex()
                        )
                        self.community.ez_send(p, announcement)
                
                transactions = self.data_manager.get_unprocessed_transactions()
                mempool_txs = [tx for nonce, tx in self.data_manager.mempool.items() if nonce not in {t.nonce for t in transactions}]
                transactions.extend(mempool_txs)
                self.logger.info(f"Round {self.pos_round_number}: Total transactions to propose: {len(transactions)}")
                
                if not transactions:
                    self.logger.info(f"Round {self.pos_round_number}: No transactions to propose.")
                    await asyncio.sleep(self.POS_ROUND_INTERVAL)
                    continue
                
                transaction_hashes = [tx.nonce for tx in transactions]
                merkle_tree = MerkleTree(transaction_hashes)
                merkle_root = merkle_tree.get_root()
                if not merkle_root:
                    self.logger.error(f"Round {self.pos_round_number}: Failed to generate Merkle root.")
                    await asyncio.sleep(self.POS_ROUND_INTERVAL)
                    continue
                
                round_seed_hex = seed.hex()
                proposer_pubkey_hex = self.data_manager.pubkey_bytes.hex()
                previous_block_hash = self.get_latest_block_hash()
                block_timestamp = int(time.time())
                block_data_to_sign = f"{round_seed_hex}:{merkle_root}:{proposer_pubkey_hex}:{previous_block_hash}:{block_timestamp}".encode()
                
                try:
                    signature_hex = self.data_manager.sk.sign(block_data_to_sign).hex()
                    proposed_block = ProposedBlockPayload(
                        round_seed_hex=round_seed_hex,
                        transaction_hashes_str=",".join(transaction_hashes),
                        merkle_root=merkle_root,
                        proposer_pubkey_hex=proposer_pubkey_hex,
                        signature=signature_hex,
                        previous_block_hash=previous_block_hash,
                        timestamp=block_timestamp
                    )
                    selected_peers = self.select_propagation_peers(5)
                    if selected_peers:
                        for peer in selected_peers:
                            self.community.ez_send(peer, proposed_block)
                        for tx_nonce in transaction_hashes:
                            if tx_nonce in self.data_manager.mempool:
                                self.data_manager.pending_transactions[tx_nonce] = self.data_manager.mempool[tx_nonce]
                        self.store_proposed_block(proposed_block)
                        self.logger.info(f"Round {self.pos_round_number}: Proposed block with {len(transaction_hashes)} transactions.")
                    else:
                        self.logger.warning(f"Round {self.pos_round_number}: No peers available for propagation")
                except Exception as e:
                    self.logger.error(f"Round {self.pos_round_number}: Error proposing block: {e}")
            else:
                self.logger.info(f"Waiting to be selected as validator for round {seed.hex()[:8]}")
            
            await asyncio.sleep(self.POS_ROUND_INTERVAL)
    
    async def handle_proposed_block(self, peer: Peer, payload: ProposedBlockPayload) -> None:
        """Handle a proposed block."""
        if payload.previous_block_hash != self.get_latest_block_hash():
            fork_resolved = await self.resolve_fork_with_retry(payload)
            if not fork_resolved:
                self.logger.warning(f"Block hash mismatch. Expected {self.get_latest_block_hash()[:16]}, got {payload.previous_block_hash[:16]}.")
                return
            self.logger.info("Fork successfully resolved!")
        
        try:
            pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.proposer_pubkey_hex))
            data = f"{payload.round_seed_hex}:{payload.merkle_root}:{payload.proposer_pubkey_hex}:{payload.previous_block_hash}:{payload.timestamp}".encode()
            pubkey.verify(bytes.fromhex(payload.signature), data)
            self.logger.info(f"Block signature verified for {payload.proposer_pubkey_hex[:8]}.")
        except InvalidSignature:
            self.logger.warning(f"Block signature invalid for {payload.proposer_pubkey_hex[:8]}.")
            return
        except Exception as e:
            self.logger.error(f"Error verifying block signature: {e}")
            return
        
        if not payload.transaction_hashes_str:
            if payload.merkle_root != MerkleTree([]).get_root():
                self.logger.warning(f"Empty block has invalid Merkle root {payload.merkle_root}.")
                return
            self.logger.info("Empty block with consistent Merkle root.")
        else:
            try:
                tx_hashes = payload.transaction_hashes_str.split(",")
                reconstructed_merkle = MerkleTree(tx_hashes)
                if reconstructed_merkle.get_root() != payload.merkle_root:
                    self.logger.warning(f"Merkle root mismatch. Expected {payload.merkle_root}.")
                    return
                self.logger.info(f"Merkle root verified for {len(tx_hashes)} transactions.")
            except Exception as e:
                self.logger.error(f"Error verifying Merkle root: {e}")
                return
        
        self.logger.info(f"Block from {payload.proposer_pubkey_hex[:8]} passed verifications.")
        if self.data_manager.stakes[self.data_manager.pubkey_bytes] >= self.MIN_STAKE:
            await self.send_validator_vote(payload)
        else:
            self.logger.info(f"Not voting due to insufficient stake.")
    
    async def send_validator_vote(self, block: ProposedBlockPayload) -> None:
        """Send a validator vote."""
        block_id = f"{block.round_seed_hex}:{block.merkle_root}"
        if block_id in self.processed_blocks:
            self.logger.info(f"Already processed block {block_id[:16]}.")
            return
        
        vote_data = f"{block.round_seed_hex}:{block.merkle_root}:{block.proposer_pubkey_hex}:{self.data_manager.pubkey_bytes.hex()}:true"
        vote_signature = self.data_manager.sk.sign(vote_data.encode()).hex()
        vote = ValidatorVote(
            round_seed_hex=block.round_seed_hex,
            block_merkle_root=block.merkle_root,
            proposer_pubkey_hex=block.proposer_pubkey_hex,
            validator_pubkey_hex=self.data_manager.pubkey_bytes.hex(),
            vote=True,
            signature=vote_signature
        )
        
        self.block_votes.setdefault(block_id, {})[self.data_manager.pubkey_bytes.hex()] = True
        selected_peers = self.select_propagation_peers(3)
        for peer in selected_peers:
            try:
                self.community.ez_send(peer, vote)
                self.logger.debug(f"Sent vote for block {block_id[:16]} to {peer.mid.hex()[:8]}")
            except Exception as e:
                self.logger.warning(f"Failed to send vote to {peer.mid.hex()[:8]}: {e}")
        
        self.processed_blocks.add(block_id)
        await self.check_consensus(block)
    
    async def handle_validator_vote(self, peer: Peer, payload: ValidatorVote) -> None:
        """Handle a validator vote."""
        block_id = f"{payload.round_seed_hex}:{payload.block_merkle_root}"
        self.logger.info(f"Received vote for block {block_id[:16]} from {payload.validator_pubkey_hex[:8]}")
        
        try:
            pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.validator_pubkey_hex))
            vote_data = f"{payload.round_seed_hex}:{payload.block_merkle_root}:{payload.proposer_pubkey_hex}:{payload.validator_pubkey_hex}:{'true' if payload.vote else 'false'}"
            pubkey.verify(bytes.fromhex(payload.signature), vote_data.encode())
        except Exception as e:
            self.logger.warning(f"Invalid vote signature: {e}")
            return
        
        self.block_votes.setdefault(block_id, {})[payload.validator_pubkey_hex] = payload.vote
        if block_id not in self.processed_blocks:
            selected_peers = self.select_propagation_peers(2)
            for forward_peer in selected_peers:
                if forward_peer.mid.hex() != peer.mid.hex():
                    try:
                        self.community.ez_send(forward_peer, payload)
                        self.logger.debug(f"Forwarded vote for {block_id[:16]} to {forward_peer.mid.hex()[:8]}")
                    except Exception as e:
                        self.logger.warning(f"Failed to forward vote: {e}")
        
        if payload.proposer_pubkey_hex == self.data_manager.pubkey_bytes.hex():
            proposed_blocks_db = self.db_env.open_db(b'proposed_blocks', create=True)
            try:
                with self.db_env.begin(db=proposed_blocks_db) as txn:
                    for key, data in txn.cursor():
                        key_str = key.decode()
                        if key_str.startswith(f"{payload.round_seed_hex}:"):
                            proposed_block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, data)
                            if proposed_block.merkle_root == payload.block_merkle_root:
                                await self.check_consensus(proposed_block)
                                return
                self.logger.warning(f"Vote for unknown block {block_id[:16]}")
            except Exception as e:
                self.logger.error(f"Error retrieving proposed block: {e}")
    
    async def check_consensus(self, block: ProposedBlockPayload) -> None:
        """Check if consensus is reached."""
        block_id = f"{block.round_seed_hex}:{block.merkle_root}"
        if block_id in self.block_confirmations:
            return
        
        votes = self.block_votes.get(block_id, {})
        total_stake = 0
        approving_stake = 0
        for voter_pubkey, vote in votes.items():
            try:
                voter_stake = self.data_manager.stakes.get(bytes.fromhex(voter_pubkey), 0)
                total_stake += voter_stake
                if vote:
                    approving_stake += voter_stake
            except Exception as e:
                self.logger.warning(f"Error counting stake for {voter_pubkey[:8]}: {e}")
        
        if total_stake > 0 and approving_stake / total_stake >= self.QUORUM_RATIO:
            self.logger.info(f"Consensus reached for {block_id[:16]} with {approving_stake}/{total_stake} stake")
            confirmation_data = f"{block.round_seed_hex}:{block.merkle_root}:{block.proposer_pubkey_hex}:{block.timestamp}:{len(votes)}"
            confirmation_signature = self.data_manager.sk.sign(confirmation_data.encode()).hex()
            confirmation = BlockConfirmation(
                round_seed_hex=block.round_seed_hex,
                block_merkle_root=block.merkle_root,
                proposer_pubkey_hex=block.proposer_pubkey_hex,
                timestamp=block.timestamp,
                signatures_count=len(votes),
                confirmer_pubkey_hex=self.data_manager.pubkey_bytes.hex(),
                signature=confirmation_signature
            )
            self.block_confirmations[block_id] = confirmation
            for peer in self.community.get_peers():
                try:
                    self.community.ez_send(peer, confirmation)
                except Exception as e:
                    self.logger.warning(f"Failed to send confirmation: {e}")
            await self.add_confirmed_block(block)
        else:
            self.logger.info(f"Not enough votes for {block_id[:16]}: {approving_stake}/{total_stake} vs {self.QUORUM_RATIO}")
    
    async def handle_block_confirmation(self, peer: Peer, payload: BlockConfirmation) -> None:
        """Handle a block confirmation."""
        block_id = f"{payload.round_seed_hex}:{payload.block_merkle_root}"
        self.logger.info(f"Received confirmation for {block_id[:16]} from {payload.confirmer_pubkey_hex[:8]}")
        
        try:
            pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.confirmer_pubkey_hex))
            data = f"{payload.round_seed_hex}:{payload.block_merkle_root}:{payload.proposer_pubkey_hex}:{payload.timestamp}:{payload.signatures_count}"
            pubkey.verify(bytes.fromhex(payload.signature), data.encode())
        except Exception as e:
            self.logger.warning(f"Invalid confirmation signature: {e}")
            return
        
        if block_id not in self.block_confirmations:
            self.block_confirmations[block_id] = payload
            selected_peers = self.select_propagation_peers(3)
            for forward_peer in selected_peers:
                if forward_peer.mid.hex() != peer.mid.hex():
                    try:
                        self.community.ez_send(forward_peer, payload)
                    except Exception as e:
                        self.logger.warning(f"Failed to forward confirmation: {e}")
            
            proposed_blocks_db = self.db_env.open_db(b'proposed_blocks', create=True)
            try:
                with self.db_env.begin(db=proposed_blocks_db) as txn:
                    for key, data in txn.cursor():
                        key_str = key.decode()
                        if key_str.startswith(f"{payload.round_seed_hex}:"):
                            proposed_block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, data)
                            if proposed_block.merkle_root == payload.block_merkle_root:
                                await self.add_confirmed_block(proposed_block)
                                return
                self.logger.warning(f"Confirmation for unknown block {block_id[:16]}")
            except Exception as e:
                self.logger.error(f"Error retrieving proposed block: {e}")
    
    async def add_confirmed_block(self, block: ProposedBlockPayload) -> None:
        """Add a confirmed block to the blockchain."""
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        block_data = f"{block.round_seed_hex}:{block.merkle_root}:{block.proposer_pubkey_hex}:{block.previous_block_hash}:{block.timestamp}"
        block_hash = hashlib.sha256(block_data.encode()).hexdigest()
        
        try:
            serialized_block = default_serializer.pack_serializable(block)
            with self.db_env.begin(db=blocks_db, write=True) as txn:
                txn.put(block_hash.encode(), serialized_block)
            self.logger.info(f"Added confirmed block {block_hash[:16]} with {len(block.transaction_hashes_str.split(','))} transactions")
            self.data_manager.mark_transactions_as_processed(block.transaction_hashes_str.split(","))
            await self.reward_proposer(block.proposer_pubkey_hex)
            self.current_chain_head = block_hash
        except Exception as e:
            self.logger.error(f"Failed to add confirmed block: {e}")
    
    async def reward_proposer(self, proposer_pubkey_hex: str) -> None:
        """Reward the proposer with stake."""
        try:
            proposer_pubkey_bytes = bytes.fromhex(proposer_pubkey_hex)
            reward_amount = 2
            current_stake = self.data_manager.stakes.get(proposer_pubkey_bytes, 0)
            new_stake = current_stake + reward_amount
            with self.db_env.begin(db=self.data_manager.stake_db, write=True) as txn:
                txn.put(proposer_pubkey_bytes, str(new_stake).encode())
            self.data_manager.stakes[proposer_pubkey_bytes] = new_stake
            if proposer_pubkey_hex == self.data_manager.pubkey_bytes.hex():
                self.logger.info(f"Received reward of {reward_amount} stake. Total: {new_stake}")
            else:
                self.logger.info(f"Awarded {reward_amount} stake to {proposer_pubkey_hex[:8]}. Total: {new_stake}")
        except Exception as e:
            self.logger.error(f"Failed to reward proposer {proposer_pubkey_hex[:8]}: {e}")
    
    def get_latest_block_hash(self) -> str:
        """Get the latest block hash."""
        if self.current_chain_head:
            return self.current_chain_head
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        latest_hash = ""
        with self.db_env.begin(db=blocks_db) as txn:
            cursor = txn.cursor()
            if cursor.last():
                latest_hash = cursor.key().decode()
        self.current_chain_head = latest_hash
        return latest_hash
    
    def find_latest_block_hash(self) -> str:
        """Find the latest block hash in the database."""
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        latest_hash = ""
        with self.db_env.begin(db=blocks_db) as txn:
            cursor = txn.cursor()
            if cursor.last():
                latest_hash = cursor.key().decode()
        return latest_hash
    
    def select_propagation_peers(self, count: int = 5) -> List[Peer]:
        """Select peers for gossip propagation."""
        peers = self.community.get_peers()
        if not peers:
            return []
        if len(peers) <= count:
            return peers
        sorted_peers = sorted(peers, key=lambda p: p.mid)
        peer_index = self.pos_round_number % len(sorted_peers)
        selected = []
        for i in range(count):
            idx = (peer_index + i) % len(sorted_peers)
            selected.append(sorted_peers[idx])
        return selected
    
    def store_proposed_block(self, block: ProposedBlockPayload) -> None:
        """Store a proposed block."""
        proposed_blocks_db = self.db_env.open_db(b'proposed_blocks', create=True)
        block_id = f"{block.round_seed_hex}:{block.proposer_pubkey_hex[:8]}".encode()
        serialized_block = default_serializer.pack_serializable(block)
        with self.db_env.begin(db=proposed_blocks_db, write=True) as txn:
            txn.put(block_id, serialized_block)
        self.logger.info(f"Stored proposed block with ID {block_id.decode()}")
    
    async def sync_blockchain_data(self) -> bool:
        """Synchronize blockchain data."""
        peers = self.community.get_peers()
        if not peers:
            return False
        latest_hash = self.get_latest_block_hash()
        request_hash = latest_hash if latest_hash else "0" * 64
        sync_requests_sent = 0
        for peer in peers[:3]:
            try:
                request = BlockSyncRequest(request_hash, count=100)
                self.community.ez_send(peer, request)
                sync_requests_sent += 1
                self.logger.info(f"Sent sync request to {peer.mid.hex()[:8]}")
            except Exception as e:
                self.logger.error(f"Error sending sync request to {peer.mid.hex()[:8]}: {e}")
        
        if sync_requests_sent == 0:
            return False
        
        start_time = time.time()
        self.sync_responses_received = 0
        while time.time() - start_time < self.SYNC_TIMEOUT and self.sync_responses_received < sync_requests_sent:
            if hasattr(self, 'sync_complete') and self.sync_complete:
                return True
            await asyncio.sleep(1)
        self.logger.warning(f"Sync timeout after {self.SYNC_TIMEOUT}s with {self.sync_responses_received} responses")
        return False
    
    async def handle_block_sync_request(self, peer: Peer, payload: BlockSyncRequest) -> None:
        """Handle a block sync request."""
        self.logger.info(f"Received sync request for {payload.block_hash[:16]} from {peer.mid.hex()[:8]}")
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        blocks = {}
        with self.db_env.begin(db=blocks_db) as txn:
            current_hash = payload.block_hash
            count = 0
            while current_hash and count < payload.count:
                block_data = txn.get(current_hash.encode())
                if not block_data:
                    break
                blocks[current_hash] = block_data.hex()
                count += 1
                try:
                    block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                    current_hash = block.previous_block_hash
                except Exception as e:
                    self.logger.error(f"Error deserializing block: {e}")
                    break
        blocks_data = json.dumps(blocks)
        response = BlockSyncResponse(payload.block_hash, blocks_data)
        self.community.ez_send(peer, response)
        self.logger.info(f"Sent {len(blocks)} blocks to {peer.mid.hex()[:8]}")
    
    async def handle_block_sync_response(self, peer: Peer, payload: BlockSyncResponse) -> None:
        """Handle a block sync response."""
        self.logger.info(f"Received sync response for {payload.request_hash[:16]}")
        try:
            blocks = json.loads(payload.blocks_data)
            blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
            new_blocks_count = 0
            with self.db_env.begin(db=blocks_db, write=True) as txn:
                for block_hash, block_data_hex in blocks.items():
                    if txn.get(block_hash.encode()):
                        continue
                    block_data = bytes.fromhex(block_data_hex)
                    block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                    if abs(time.time() - block.timestamp) > self.MAX_BLOCK_AGE:
                        self.logger.warning(f"Skipping old block {block_hash[:16]}")
                        continue
                    txn.put(block_hash.encode(), block_data)
                    new_blocks_count += 1
            self.logger.info(f"Stored {new_blocks_count} new blocks")
            
            if new_blocks_count > 0:
                self.sync_complete = True
                latest_hash = self.find_latest_block_hash()
                if latest_hash:
                    self.current_chain_head = latest_hash
                    self.logger.info(f"Updated chain head to {latest_hash[:16]}")
                
            if payload.request_hash in self.pending_sync_requests:
                fork_data = self.pending_sync_requests.pop(payload.request_hash)
                await self.resolve_fork_with_retry(fork_data)
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding blocks data: {e}")
        except Exception as e:
            self.logger.error(f"Error processing sync response: {e}")
    
    async def resolve_fork_with_retry(self, block: ProposedBlockPayload) -> bool:
        """Resolve a fork with retry."""
        fork_resolved = self.resolve_fork(block)
        if not fork_resolved:
            self.logger.info("Normal fork resolution failed. Requesting blocks...")
            for peer in self.community.get_peers():
                self.pending_sync_requests[block.previous_block_hash] = block
                request = BlockSyncRequest(block.previous_block_hash)
                self.community.ez_send(peer, request)
                self.logger.info(f"Sent sync request for {block.previous_block_hash[:16]} to {peer.mid.hex()[:8]}")
            return False
        return True
    
    def resolve_fork(self, block: ProposedBlockPayload) -> bool:
        """Resolve a blockchain fork."""
        self.logger.warning("Fork detected! Attempting to resolve...")
        if abs(time.time() - block.timestamp) > self.MAX_BLOCK_AGE:
            self.logger.warning(f"Proposed block too old (timestamp: {block.timestamp}).")
            return False
        
        alt_chain = self.get_chain_from_hash(block.previous_block_hash)
        if not alt_chain:
            self.logger.warning(f"No chain for hash {block.previous_block_hash[:16]}")
            return False
        
        my_chain = self.get_chain_from_hash(self.get_latest_block_hash())
        if len(alt_chain) > len(my_chain):
            self.logger.info(f"Alternative chain longer ({len(alt_chain)} > {len(my_chain)}). Switching.")
            self.reprocess_transactions(my_chain, alt_chain)
            self.current_chain_head = block.previous_block_hash
            self.logger.info(f"Chain head updated to {self.current_chain_head[:16]}")
            return True
        else:
            self.logger.info(f"Our chain longer or equal ({len(my_chain)} >= {len(alt_chain)}).")
            return False
    
    def reprocess_transactions(self, old_chain: List[str], new_chain: List[str]) -> None:
        """Reprocess transactions when switching chains."""
        self.logger.info("Reprocessing transactions when switching chains")
        common_ancestor = None
        old_blocks_set = set(old_chain)
        for block_hash in new_chain:
            if block_hash in old_blocks_set:
                common_ancestor = block_hash
                break
        
        if not common_ancestor:
            self.logger.warning("No common ancestor found, cannot reprocess")
            return
        
        transactions_to_revert = []
        transactions_to_apply = []
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        
        with self.db_env.begin(db=blocks_db) as txn:
            for block_hash in old_chain:
                if block_hash == common_ancestor:
                    break
                block_data = txn.get(block_hash.encode())
                if block_data:
                    try:
                        block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                        transactions_to_revert.extend(block.transaction_hashes_str.split(","))
                    except Exception as e:
                        self.logger.error(f"Error unpacking block {block_hash[:16]}: {e}")
        
        with self.db_env.begin(db=blocks_db) as txn:
            for block_hash in new_chain:
                if block_hash == common_ancestor:
                    break
                block_data = txn.get(block_hash.encode())
                if block_data:
                    try:
                        block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                        transactions_to_apply.extend(block.transaction_hashes_str.split(","))
                    except Exception as e:
                        self.logger.error(f"Error unpacking block {block_hash[:16]}: {e}")
        
        self.logger.info(f"Reverting {len(transactions_to_revert)} transactions, applying {len(transactions_to_apply)}")
        with self.db_env.begin(db=self.data_manager.processed_db, write=True) as txn:
            for tx_hash in transactions_to_revert:
                try:
                    txn.delete(tx_hash.encode())
                    with self.db_env.begin(db=self.data_manager.tx_db) as tx_txn:
                        tx_data = tx_txn.get(tx_hash.encode())
                        if tx_data:
                            tx, _ = default_serializer.unpack_serializable(ChessTransaction, tx_data)
                            self.data_manager.mempool[tx_hash] = tx
                except Exception as e:
                    self.logger.error(f"Error reverting transaction {tx_hash}: {e}")
        
        with self.db_env.begin(db=self.data_manager.processed_db, write=True) as txn:
            for tx_hash in transactions_to_apply:
                try:
                    txn.put(tx_hash.encode(), b'1')
                    if tx_hash in self.data_manager.mempool:
                        del self.data_manager.mempool[tx_hash]
                except Exception as e:
                    self.logger.error(f"Error applying transaction {tx_hash}: {e}")
    
    def get_chain_from_hash(self, start_hash: str, max_blocks: int = 100) -> List[str]:
        """Get a chain from a hash."""
        chain = []
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        current_hash = start_hash
        with self.db_env.begin(db=blocks_db) as txn:
            while current_hash and len(chain) < max_blocks:
                block_data = txn.get(current_hash.encode())
                if not block_data:
                    break
                chain.append(current_hash)
                try:
                    block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                    current_hash = block.previous_block_hash
                    if current_hash == "0" * 64:
                        chain.append(current_hash)
                        break
                except Exception as e:
                    self.logger.error(f"Error deserializing block: {e}")
                    break
        return chain