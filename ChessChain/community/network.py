import asyncio
import time
from typing import List
from .community0 import ChessCommunity
from ipv8.types import Peer

class Network:
    def __init__(self, community: ChessCommunity):
        self.community = community
        self.logger = community.logger
        self.pubkey_bytes = community.pubkey_bytes

    def select_propagation_peers(self, count: int = 5) -> List[Peer]:
        peers = self.community.get_peers()
        if not peers:
            return []
        if len(peers) <= count:
            return peers
        sorted_peers = sorted(peers, key=lambda p: p.mid)
        peer_index = self.community.pos_round_number % len(sorted_peers)
        selected = []
        for i in range(count):
            idx = (peer_index + i) % len(sorted_peers)
            selected.append(sorted_peers[idx])
        return selected

    async def startup_sequence(self) -> None:
        self.logger.info("Node starting up. Beginning startup sequence...")
        self.logger.info("Waiting for peer discovery (50 seconds)...")
        peer_discovery_time = 50
        start_time = time.time()
        while time.time() - start_time < peer_discovery_time:
            peers = self.community.get_peers()
            if peers:
                self.logger.info(f"Found {len(peers)} peers. Continuing startup sequence.")
                break
            await asyncio.sleep(2)
        peers = self.community.get_peers()
        if not peers:
            self.logger.warning("No peers found during discovery period. Will operate in standalone mode.")
        else:
            self.logger.info(f"Beginning blockchain synchronization with {len(peers)} peers...")
            sync_success = await self.community.sync.sync_blockchain_data()
            if sync_success:
                self.logger.info("Blockchain synchronization completed successfully.")
            else:
                self.logger.warning("Blockchain synchronization incomplete or failed. Continuing with local state.")
        self.logger.info("Starting PoS consensus rounds...")
        asyncio.create_task(self.community.consensus.pos_round())

    def on_peer_added(self, peer: Peer) -> None:
        print("New peer:", peer)