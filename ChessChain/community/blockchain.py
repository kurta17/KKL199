import hashlib
import time
from typing import List, TYPE_CHECKING

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from . import ChessCommunity
else:
    from . import ChessCommunity

from models.models import ProposedBlockPayload, ChessTransaction
from ipv8.messaging.serialization import default_serializer
from utils.merkle import MerkleTree

class Blockchain:
    def __init__(self, community: 'ChessCommunity'):
        self.community = community
        self.db_env = community.db_env
        self.logger = community.logger
        self.current_chain_head = community.current_chain_head

    def initialize_blockchain(self) -> None:
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        with self.db_env.begin(db=blocks_db) as txn:
            cursor = txn.cursor()
            if cursor.first():
                self.logger.info("Blockchain already initialized with existing blocks")
                return

        genesis_tx_hash = hashlib.sha256(f"genesis_tx_{self.community.GENESIS_TIME}".encode()).hexdigest()
        merkle_tree_genesis = MerkleTree([genesis_tx_hash])
        genesis_merkle_root = merkle_tree_genesis.get_root()
        previous_block_hash = "0" * 64

        genesis_block = ProposedBlockPayload.create(
            round_seed_hex=self.community.GENESIS_SEED,
            transaction_hashes=[genesis_tx_hash],
            merkle_root=genesis_merkle_root,
            proposer_pubkey_hex=self.community.GENESIS_PUBKEY_HEX,
            signature=self.community.GENESIS_SIGNATURE,
            previous_block_hash=previous_block_hash,
            timestamp=self.community.GENESIS_TIME
        )

        genesis_data_to_sign = f"{self.community.GENESIS_SEED}:{genesis_merkle_root}:{self.community.GENESIS_PUBKEY_HEX}:{previous_block_hash}:{self.community.GENESIS_TIME}"
        genesis_block_hash = hashlib.sha256(genesis_data_to_sign.encode('utf-8')).hexdigest()

        with self.db_env.begin(db=blocks_db, write=True) as txn:
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
        try:
            genesis_tx = ChessTransaction(
                match_id="genesis_match",
                winner="genesis",
                moves_hash="genesis_moves",
                nonce=genesis_tx_hash,
                proposer_pubkey_hex=self.community.pubkey_bytes.hex(),
                signature=self.community.sk.sign(f"genesis_match:genesis:{genesis_tx_hash}".encode()).hex()
            )
            with self.db_env.begin(db=self.community.tx_db, write=True) as txn:
                serialized_tx = default_serializer.pack_serializable(genesis_tx)
                txn.put(genesis_tx_hash.encode(), serialized_tx)
            processed_db = self.db_env.open_db(b'processed_transactions', create=True)
            with self.db_env.begin(db=processed_db, write=True) as txn:
                txn.put(genesis_tx_hash.encode(), b'1')
            self.community.transactions.add(genesis_tx_hash)
            self.logger.info(f"Created and stored genesis transaction with hash {genesis_tx_hash[:16]}")
            self.create_dummy_transactions(3)
        except Exception as e:
            self.logger.error(f"Failed to create genesis transaction: {e}")

    def get_latest_block_hash(self) -> str:
        if self.community.current_chain_head:
            return self.community.current_chain_head
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        latest_hash = ""
        with self.db_env.begin(db=blocks_db) as txn:
            cursor = txn.cursor()
            if cursor.last():
                latest_hash = cursor.key().decode('utf-8')
        self.community.current_chain_head = latest_hash
        return latest_hash

    def resolve_fork(self, proposed_block: ProposedBlockPayload) -> bool:
        self.logger.warning("Fork detected! Attempting to resolve...")
        if abs(time.time() - proposed_block.timestamp) > self.community.MAX_BLOCK_AGE:
            self.logger.warning(f"Proposed block is too old (timestamp: {proposed_block.timestamp}). Rejecting.")
            return False
        alt_chain = self.get_chain_from_hash(proposed_block.previous_block_hash)
        if not alt_chain:
            self.logger.warning(f"Unable to find alternative chain for previous hash {proposed_block.previous_block_hash[:16]}")
            return False
        my_chain = self.get_chain_from_hash(self.get_latest_block_hash())
        if len(alt_chain) > len(my_chain):
            self.logger.info(f"Alternative chain is longer ({len(alt_chain)} > {len(my_chain)}). Switching to it.")
            self.community.transaction.reprocess_transactions(my_chain, alt_chain)
            self.community.current_chain_head = proposed_block.previous_block_hash
            self.logger.info(f"Chain head updated to {self.community.current_chain_head[:16]}")
            return True
        else:
            self.logger.info(f"Our chain is longer or equal ({len(my_chain)} >= {len(alt_chain)}). Keeping it.")
            return False

    def get_chain_from_hash(self, start_hash: str, max_blocks: int = 100) -> List[str]:
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
                    if current_hash == "0" * 64:
                        chain.append(current_hash)
                        break
                except Exception as e:
                    self.logger.error(f"Error deserializing block: {e}")
                    break
        return chain

    async def add_confirmed_block(self, block: ProposedBlockPayload) -> None:
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        block_data_str = f"{block.round_seed_hex}:{block.merkle_root}:{block.proposer_pubkey_hex}:{block.previous_block_hash}:{block.timestamp}"
        block_hash = hashlib.sha256(block_data_str.encode('utf-8')).hexdigest()
        try:
            serialized_block = default_serializer.pack_serializable(block)
            with self.db_env.begin(db=blocks_db, write=True) as txn:
                txn.put(block_hash.encode('utf-8'), serialized_block)
            self.logger.info(f"Added confirmed block {block_hash[:16]} to blockchain with {len(block.transaction_hashes)} transactions")
            self.community.transaction.mark_transactions_as_processed(block.transaction_hashes)
            await self.community.consensus.reward_proposer(block.proposer_pubkey_hex)
        except Exception as e:
            self.logger.error(f"Failed to add confirmed block to blockchain: {e}")

    def create_dummy_transactions(self, count: int) -> None:
        # Placeholder for dummy transaction creation (not provided in original code)
        pass