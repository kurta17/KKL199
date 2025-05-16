import asyncio
import hashlib
import time
from typing import Dict, List
from .community0 import ChessCommunity
from models.models import ProposedBlockPayload, ProposerAnnouncement, ValidatorVote, BlockConfirmation, ChessTransaction
from ipv8.messaging.serialization import default_serializer
from utils.merkle import MerkleTree
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

class Consensus:
    def __init__(self, community: ChessCommunity):
        self.community = community
        self.logger = community.logger
        self.stakes = community.stakes
        self.block_votes = community.block_votes
        self.block_confirmations = community.block_confirmations
        self.processed_blocks = community.processed_blocks
        self.pubkey_bytes = community.pubkey_bytes
        self.sk = community.sk
        self.db_env = community.db_env

    async def pos_round(self) -> None:
        while True:
            self.community.pos_round_number += 1
            current_time = time.time()
            self.logger.info(f"Starting PoS round {self.community.pos_round_number} at {current_time}")
            seed = hashlib.sha256(str(self.community.pos_round_number).encode()).digest()
            if self.stakes[self.pubkey_bytes] < self.community.MIN_STAKE:
                print(f"Stake too low ({self.stakes[self.pubkey_bytes]}), not proposing")
                await asyncio.sleep(self.community.POS_ROUND_INTERVAL)
                continue
            proposer = self.community.proposer.checking_proposer(seed)
            if proposer:
                for p in self.community.get_peers():
                    if p.mid != self.pubkey_bytes:
                        announcement = ProposerAnnouncement(
                            round_seed_hex=seed.hex(),
                            proposer_pubkey_hex=self.pubkey_bytes.hex(),
                        )
                        serialized = default_serializer.pack_serializable(announcement)
                        self.logger.debug(f"Sending announcement: {len(serialized)} bytes, fields: {seed.hex()[:8]}, {self.pubkey_bytes.hex()[:8]}")
                        self.community.ez_send(p, announcement)
                self.logger.info(f"Announced proposer for round {seed.hex()[:8]}: {self.pubkey_bytes.hex()[:8]}")
                transactions_to_propose: List[ChessTransaction] = []
                processed_nonces = set()
                stored_transactions = self.community.transaction.get_unprocessed_transactions()
                for tx in stored_transactions:
                    if tx.nonce not in processed_nonces:
                        transactions_to_propose.append(tx)
                        processed_nonces.add(tx.nonce)
                self.logger.info(f"Round {self.community.pos_round_number}: Fetched {len(transactions_to_propose)} unprocessed transactions from DB.")
                mempool_tx_count = 0
                for nonce, tx_from_mempool in list(self.community.mempool.items()):
                    if nonce not in processed_nonces:
                        if isinstance(tx_from_mempool, ChessTransaction):
                            transactions_to_propose.append(tx_from_mempool)
                            processed_nonces.add(nonce)
                            mempool_tx_count += 1
                        else:
                            self.logger.warning(f"Mempool item with nonce {nonce} is not a ChessTransaction object, but {type(tx_from_mempool)}. Skipping.")
                if mempool_tx_count > 0:
                    self.logger.info(f"Round {self.community.pos_round_number}: Added {mempool_tx_count} unique transactions from mempool.")
                self.logger.info(f"Round {self.community.pos_round_number}: Total transactions to propose: {len(transactions_to_propose)}")
                if not transactions_to_propose:
                    self.logger.info(f"Round {self.community.pos_round_number}: No transactions in mempool or DB to propose a block for.")
                    await asyncio.sleep(self.community.POS_ROUND_INTERVAL)
                    continue
                transaction_hashes = [tx.nonce for tx in transactions_to_propose]
                if not transaction_hashes:
                    self.logger.warning(f"Round {self.community.pos_round_number}: Transaction hashes list is empty despite having transactions. This should not happen.")
                    await asyncio.sleep(self.community.POS_ROUND_INTERVAL)
                    continue
                merkle_tree = MerkleTree(transaction_hashes)
                merkle_root = merkle_tree.get_root()
                if not merkle_root:
                    self.logger.error(f"Round {self.community.pos_round_number}: Failed to generate Merkle root.")
                    await asyncio.sleep(self.community.POS_ROUND_INTERVAL)
                    continue
                self.logger.info(f"Round {self.community.pos_round_number}: Merkle root for {len(transaction_hashes)} transactions: {merkle_root}")
                round_seed_hex = seed.hex()
                proposer_pubkey_hex = self.pubkey_bytes.hex()
                previous_block_hash = self.community.blockchain.get_latest_block_hash()
                block_timestamp = int(time.time())
                block_data_to_sign_str = f"{round_seed_hex}:{merkle_root}:{proposer_pubkey_hex}:{previous_block_hash}:{block_timestamp}"
                block_data_to_sign_bytes = block_data_to_sign_str.encode('utf-8')
                try:
                    signature_hex = self.sk.sign(block_data_to_sign_bytes).hex()
                except Exception as e:
                    self.logger.error(f"Round {self.community.pos_round_number}: Error signing block data: {e}")
                    await asyncio.sleep(self.community.POS_ROUND_INTERVAL)
                    continue
                try:
                    proposed_block = ProposedBlockPayload(
                        round_seed_hex=round_seed_hex,
                        transaction_hashes_str=",".join(transaction_hashes),
                        merkle_root=merkle_root,
                        proposer_pubkey_hex=proposer_pubkey_hex,
                        signature=signature_hex,
                        timestamp=block_timestamp,
                        previous_block_hash=previous_block_hash
                    )
                    self.logger.info(f"Round {self.community.pos_round_number}: Proposing block with Merkle root {merkle_root}, timestamp {block_timestamp}, and {len(transaction_hashes)} transactions.")
                    selected_peers = self.community.network.select_propagation_peers(5)
                    if selected_peers:
                        for peer in selected_peers:
                            try:
                                self.community.ez_send(peer, proposed_block)
                                self.logger.debug(f"Round {self.community.pos_round_number}: Sent block proposal to peer {peer.mid.hex()[:8]}")
                            except Exception as e:
                                self.logger.warning(f"Round {self.community.pos_round_number}: Failed to send block to peer {peer.mid.hex()[:8]}: {e}")
                        pending_count = 0
                        for tx_nonce in transaction_hashes:
                            if tx_nonce in self.community.mempool:
                                self.community.pending_transactions[tx_nonce] = self.community.mempool[tx_nonce]
                                pending_count += 1
                        self.community.proposer.store_proposed_block(proposed_block)
                        self.logger.info(f"Round {self.community.pos_round_number}: Marked {pending_count} proposed transactions as pending confirmation.")
                    else:
                        self.logger.warning(f"Round {self.community.pos_round_number}: No peers available for block propagation")
                except Exception as e:
                    self.logger.error(f"Round {self.community.pos_round_number}: Error creating or sending proposed block: {e}")
            else:
                self.logger.info(f"Waiting to be selected as validator for round {self.community.pos_round_number} with seed {seed.hex()[:8]}")
            await asyncio.sleep(self.community.POS_ROUND_INTERVAL)

    async def send_validator_vote(self, block: ProposedBlockPayload) -> None:
        block_id = f"{block.round_seed_hex}:{block.merkle_root}"
        if block_id in self.processed_blocks:
            self.logger.info(f"Already processed block {block_id[:16]}. Skipping vote.")
            return
        vote_data = f"{block.round_seed_hex}:{block.merkle_root}:{block.proposer_pubkey_hex}:{self.pubkey_bytes.hex()}:true"
        vote_signature = self.sk.sign(vote_data.encode('utf-8')).hex()
        vote = ValidatorVote(
            round_seed_hex=block.round_seed_hex,
            block_merkle_root=block.merkle_root,
            proposer_pubkey_hex=block.proposer_pubkey_hex,
            validator_pubkey_hex=self.pubkey_bytes.hex(),
            vote=True,
            signature=vote_signature
        )
        if block_id not in self.block_votes:
            self.block_votes[block_id] = {}
        self.block_votes[block_id][self.pubkey_bytes.hex()] = True
        selected_peers = self.community.network.select_propagation_peers(3)
        if selected_peers:
            for peer in selected_peers:
                try:
                    self.community.ez_send(peer, vote)
                    self.logger.debug(f"Sent vote for block {block_id[:16]} to {peer.mid.hex()[:8]}")
                except Exception as e:
                    self.logger.warning(f"Failed to send vote to {peer.mid.hex()[:8]}: {e}")
        self.processed_blocks.add(block_id)
        await self.check_consensus(block)

    async def on_validator_vote(self, peer: Peer, payload: ValidatorVote) -> None:
        block_id = f"{payload.round_seed_hex}:{payload.block_merkle_root}"
        self.logger.info(f"Received validator vote for block {block_id[:16]} from {payload.validator_pubkey_hex[:8]}")
        try:
            validator_pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.validator_pubkey_hex))
            vote_data = f"{payload.round_seed_hex}:{payload.block_merkle_root}:{payload.proposer_pubkey_hex}:{payload.validator_pubkey_hex}:{'true' if payload.vote else 'false'}"
            validator_pubkey.verify(bytes.fromhex(payload.signature), vote_data.encode('utf-8'))
        except Exception as e:
            self.logger.warning(f"Invalid vote signature from {payload.validator_pubkey_hex[:8]}: {e}")
            return
        if block_id not in self.block_votes:
            self.block_votes[block_id] = {}
        self.block_votes[block_id][payload.validator_pubkey_hex] = payload.vote
        if block_id not in self.processed_blocks:
            selected_peers = self.community.network.select_propagation_peers(2)
            if selected_peers:
                for forward_peer in selected_peers:
                    if forward_peer.mid.hex() != peer.mid.hex():
                        try:
                            self.community.ez_send(forward_peer, payload)
                            self.logger.debug(f"Forwarded vote for block {block_id[:16]} to {forward_peer.mid.hex()[:8]}")
                        except Exception as e:
                            self.logger.warning(f"Failed to forward vote to {forward_peer.mid.hex()[:8]}: {e}")
        if payload.proposer_pubkey_hex == self.pubkey_bytes.hex():
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
        block_id = f"{block.round_seed_hex}:{block.merkle_root}"
        if block_id in self.block_confirmations:
            return
        if block_id not in self.block_votes:
            return
        votes = self.block_votes[block_id]
        total_stake = 0
        approving_stake = 0
        for voter_pubkey, vote in votes.items():
            try:
                voter_stake = self.stakes.get(bytes.fromhex(voter_pubkey), 0)
                total_stake += voter_stake
                if vote:
                    approving_stake += voter_stake
            except Exception as e:
                self.logger.warning(f"Error counting stake for voter {voter_pubkey[:8]}: {e}")
        if total_stake > 0 and approving_stake / total_stake >= self.community.QUORUM_RATIO:
            self.logger.info(f"Consensus reached for block {block_id[:16]} with {approving_stake}/{total_stake} stake ({approving_stake/total_stake:.2f})")
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
            self.block_confirmations[block_id] = confirmation
            for peer in self.community.get_peers():
                try:
                    self.community.ez_send(peer, confirmation)
                except Exception as e:
                    self.logger.warning(f"Failed to send confirmation to {peer.mid.hex()[:8]}: {e}")
            await self.community.blockchain.add_confirmed_block(block)
        else:
            self.logger.info(f"Not enough votes for block {block_id[:16]} yet: {approving_stake}/{total_stake} stake ({approving_stake/total_stake:.2f} vs required {self.community.QUORUM_RATIO})")

    async def on_block_confirmation(self, peer: Peer, payload: BlockConfirmation) -> None:
        block_id = f"{payload.round_seed_hex}:{payload.block_merkle_root}"
        self.logger.info(f"Received block confirmation for {block_id[:16]} from {payload.confirmer_pubkey_hex[:8]} with {payload.signatures_count} signatures")
        try:
            confirmer_pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload.confirmer_pubkey_hex))
            confirmation_data = f"{payload.round_seed_hex}:{payload.block_merkle_root}:{payload.proposer_pubkey_hex}:{payload.timestamp}:{payload.signatures_count}"
            confirmer_pubkey.verify(bytes.fromhex(payload.signature), confirmation_data.encode('utf-8'))
        except Exception as e:
            self.logger.warning(f"Invalid confirmation signature from {payload.confirmer_pubkey_hex[:8]}: {e}")
            return
        if block_id not in self.block_confirmations:
            self.block_confirmations[block_id] = payload
            selected_peers = self.community.network.select_propagation_peers(3)
            if selected_peers:
                for forward_peer in selected_peers:
                    if forward_peer.mid.hex() != peer.mid.hex():
                        try:
                            self.community.ez_send(forward_peer, payload)
                            self.logger.debug(f"Forwarded confirmation for block {block_id[:16]} to {forward_peer.mid.hex()[:8]}")
                        except Exception as e:
                            self.logger.warning(f"Failed to forward confirmation to {forward_peer.mid.hex()[:8]}: {e}")
            proposed_blocks_db = self.db_env.open_db(b'proposed_blocks', create=True)
            try:
                with self.db_env.begin(db=proposed_blocks_db) as txn:
                    for key, data in txn.cursor():
                        key_str = key.decode('utf-8')
                        if key_str.startswith(f"{payload.round_seed_hex}:"):
                            proposed_block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, data)
                            if proposed_block.merkle_root == payload.block_merkle_root:
                                await self.community.blockchain.add_confirmed_block(proposed_block)
                                return
                self.logger.warning(f"Received confirmation for unknown block {block_id[:16]}")
            except Exception as e:
                self.logger.error(f"Error retrieving proposed block for confirmation: {e}")

    async def reward_proposer(self, proposer_pubkey_hex: str) -> None:
        try:
            proposer_pubkey_bytes = bytes.fromhex(proposer_pubkey_hex)
            reward_amount = 2
            current_stake = self.stakes.get(proposer_pubkey_bytes, 0)
            new_stake = current_stake + reward_amount
            with self.db_env.begin(db=self.community.stake_db, write=True) as txn:
                txn.put(proposer_pubkey_bytes, str(new_stake).encode('utf-8'))
            self.stakes[proposer_pubkey_bytes] = new_stake
            if proposer_pubkey_hex == self.pubkey_bytes.hex():
                self.logger.info(f"Received block proposal reward of {reward_amount} stake. New total: {new_stake}")
            else:
                self.logger.info(f"Awarded block proposal reward of {reward_amount} stake to {proposer_pubkey_hex[:8]}. Their new total: {new_stake}")
        except Exception as e:
            self.logger.error(f"Failed to reward proposer {proposer_pubkey_hex[:8]}: {e}")