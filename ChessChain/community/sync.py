import asyncio
import json
import time
from typing import TYPE_CHECKING

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from . import ChessCommunity
else:
    from . import ChessCommunity

from models.models import BlockSyncRequest, BlockSyncResponse, ProposedBlockPayload
from ipv8.types import Peer
from ipv8.messaging.serialization import default_serializer

class Sync:
    def __init__(self, community: 'ChessCommunity'):
        self.community = community
        self.logger = community.logger
        self.db_env = community.db_env
        self.pending_sync_requests = community.pending_sync_requests
        self.sync_complete = False
        self.sync_responses_received = 0

    async def resolve_fork_with_retry(self, block: ProposedBlockPayload) -> bool:
        fork_resolved = self.community.blockchain.resolve_fork(block)
        if not fork_resolved:
            self.logger.info(f"Normal fork resolution failed. Requesting blocks from peer chain...")
            for peer in self.community.get_peers():
                self.pending_sync_requests[block.previous_block_hash] = block
                request = BlockSyncRequest(block.previous_block_hash)
                self.community.ez_send(peer, request)
                self.logger.info(f"Sent block sync request for {block.previous_block_hash[:16]} to {peer.mid.hex()[:8]}")
            return False
        return True

    async def on_block_sync_request(self, peer: Peer, payload: BlockSyncRequest) -> None:
        self.logger.info(f"Received block sync request for {payload.block_hash[:16]} from {peer.mid.hex()[:8]}")
        blocks = {}
        blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
        with self.db_env.begin(db=blocks_db) as txn:
            current_hash = payload.block_hash
            count = 0
            while current_hash and count < payload.count:
                block_data = txn.get(current_hash.encode('utf-8'))
                if not block_data:
                    break
                blocks[current_hash] = block_data.hex()
                count += 1
                try:
                    block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                    current_hash = block.previous_block_hash
                except Exception as e:
                    self.logger.error(f"Error deserializing block during sync: {e}")
                    break
        blocks_data = json.dumps(blocks)
        response = BlockSyncResponse(payload.block_hash, blocks_data)
        self.community.ez_send(peer, response)
        self.logger.info(f"Sent {len(blocks)} blocks in sync response to {peer.mid.hex()[:8]}")

    async def on_block_sync_response(self, peer: Peer, payload: BlockSyncResponse) -> None:
        self.logger.info(f"Received block sync response for {payload.request_hash[:16]} with blocks")
        try:
            blocks = json.loads(payload.blocks_data)
            blocks_db = self.db_env.open_db(b'confirmed_blocks', create=True)
            new_blocks_count = 0
            with self.db_env.begin(db=blocks_db, write=True) as txn:
                for block_hash, block_data_hex in blocks.items():
                    if txn.get(block_hash.encode('utf-8')):
                        continue
                    block_data = bytes.fromhex(block_data_hex)
                    block, _ = default_serializer.unpack_serializable(ProposedBlockPayload, block_data)
                    if abs(time.time() - block.timestamp) > self.community.MAX_BLOCK_AGE:
                        self.logger.warning(f"Skipping old block {block_hash[:16]}")
                        continue
                    txn.put(block_hash.encode('utf-8'), block_data)
                    new_blocks_count += 1
            self.logger.info(f"Stored {new_blocks_count} new blocks in database")
            if new_blocks_count > 0:
                self.sync_complete = True
                latest_hash = self.community.blockchain.get_latest_block_hash()
                if latest_hash:
                    self.community.current_chain_head = latest_hash
                    self.logger.info(f"Updated chain head to {latest_hash[:16]}")
            if payload.request_hash in self.pending_sync_requests:
                fork_data = self.pending_sync_requests.pop(payload.request_hash)
                await self.resolve_fork_with_retry(fork_data)
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding blocks data: {e}")
        except Exception as e:
            self.logger.error(f"Error processing sync response: {e}")

    async def sync_blockchain_data(self) -> bool:
        sync_complete = False
        sync_timeout = 60
        peers = self.community.get_peers()
        if not peers:
            return False
        latest_hash = self.community.blockchain.get_latest_block_hash()
        if not latest_hash:
            self.logger.info("No existing blocks found. Requesting complete blockchain.")
            request_hash = "0" * 64
        else:
            self.logger.info(f"Latest known block: {latest_hash[:16]}. Requesting newer blocks.")
            request_hash = latest_hash
        sync_requests_sent = 0
        for peer in peers[:3]:
            try:
                request = BlockSyncRequest(request_hash, count=100)
                self.community.ez_send(peer, request)
                sync_requests_sent += 1
                self.logger.info(f"Sent blockchain sync request to {peer.mid.hex()[:8]}")
            except Exception as e:
                self.logger.error(f"Error sending sync request to peer {peer.mid.hex()[:8]}: {e}")
        if sync_requests_sent == 0:
            return False
        start_time = time.time()
        self.sync_responses_received = 0
        while time.time() - start_time < sync_timeout and self.sync_responses_received < sync_requests_sent:
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