import asyncio
from typing import List
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from ipv8.messaging.serialization import default_serializer
from .community0 import ChessCommunity
from models.models import ChessTransaction, ProposedBlockPayload
from ipv8.types import Peer

class Transaction:
    def __init__(self, community: ChessCommunity):
        self.community = community
        self.logger = community.logger
        self.db_env = community.db_env
        self.mempool = community.mempool
        self.transactions = community.transactions
        self.sent = community.sent
        self.pending_transactions = community.pending_transactions
        self.tx_db = community.tx_db

    async def periodic_broadcast(self) -> None:
        while True:
            for tx in list(self.mempool.values()):
                for p in self.community.get_peers():
                    if p.mid != self.community.pubkey_bytes and (p.mid, tx.nonce) not in self.sent:
                        self.community.ez_send(p, tx)
                        self.sent.add((p.mid, tx.nonce))
            await asyncio.sleep(5)

    def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
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

    def send_transaction(self, tx: ChessTransaction) -> None:
        if tx.nonce in self.transactions:
            print(f"Transaction {tx.nonce} already exists")
            return
        if not hasattr(tx, 'verify_signatures') or not tx.verify_signatures():
            print(f"Transaction {tx.nonce} failed verification")
            return
        with self.db_env.begin(db=self.tx_db, write=True) as wr:
            serialized_tx = default_serializer.pack_serializable(tx)
            wr.put(tx.nonce.encode(), serialized_tx)
        self.transactions.add(tx.nonce)
        self.mempool[tx.nonce] = tx
        for p in self.community.get_peers():
            if p.mid != self.community.pubkey_bytes and (p.mid, tx.nonce) not in self.sent:
                self.community.ez_send(p, tx)
                self.sent.add((p.mid, tx.nonce))
        print(f"Sent transaction {tx.nonce}")

    def get_unprocessed_transactions(self) -> List[ChessTransaction]:
        out = []
        processed_db = self.db_env.open_db(b'processed_transactions', create=True)
        with self.db_env.begin(db=self.tx_db) as txn:
            with self.db_env.begin(db=processed_db) as processed_txn:
                for key, raw in txn.cursor():
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
        processed_db = self.db_env.open_db(b'processed_transactions', create=True)
        with self.db_env.begin(db=processed_db, write=True) as txn:
            for tx_hash in transaction_hashes:
                txn.put(tx_hash.encode(), b'1')
                if tx_hash in self.pending_transactions:
                    del self.pending_transactions[tx_hash]
                if tx_hash in self.mempool:
                    del self.mempool[tx_hash]

    def reprocess_transactions(self, old_chain: List[str], new_chain: List[str]) -> None:
        self.logger.info(f"Reprocessing transactions when switching chains")
        common_ancestor = None
        old_blocks_set = set(old_chain)
        for block_hash in new_chain:
            if block_hash in old_blocks_set:
                common_ancestor = block_hash
                break
        if not common_ancestor:
            self.logger.warning("No common ancestor found between chains, cannot safely reprocess transactions")
            return
        transactions_to_revert = []
        transactions_to_apply = []
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
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
        processed_db = self.db_env.open_db(b'processed_transactions', create=True)
        with self.db_env.begin(db=processed_db, write=True) as txn:
            for tx_hash in transactions_to_revert:
                try:
                    txn.delete(tx_hash.encode())
                    with self.db_env.begin(db=self.tx_db) as tx_txn:
                        tx_data = tx_txn.get(tx_hash.encode())
                        if tx_data:
                            tx, _ = default_serializer.unpack_serializable(ChessTransaction, tx_data)
                            self.mempool[tx_hash] = tx
                except Exception as e:
                    self.logger.error(f"Error reverting transaction {tx_hash}: {e}")
        with self.db_env.begin(db=processed_db, write=True) as txn:
            for tx_hash in transactions_to_apply:
                try:
                    txn.put(tx_hash.encode(), b'1')
                    if tx_hash in self.mempool:
                        del self.mempool[tx_hash]
                except Exception as e:
                    self.logger.error(f"Error applying transaction {tx_hash}: {e}")

    def is_transaction_in_db(self, nonce: str) -> bool:
        with self.db_env.begin(db=self.tx_db, write=False) as txn:
            return txn.get(nonce.encode('utf-8')) is not None