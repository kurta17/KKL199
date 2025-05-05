import os
import asyncio
from asyncio import run
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs
from ipv8.util import run_forever
from ipv8.community import Community, CommunitySettings
from ipv8_service import IPv8
import networkx as nx
from pyvis.network import Network

class MyCommunity(Community):
    community_id = os.urandom(20)
    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.network.add_peer_observer(self)
    def started(self) -> None:
        print(f"MyCommunity started for peer: {self.my_peer}")
    def on_peer_added(self, peer):
        a = self.my_peer.mid.hex()
        b = peer.mid.hex()
        G.add_edge(a, b)
    def on_peer_removed(self, peer):
        a = self.my_peer.mid.hex()
        b = peer.mid.hex()
        if G.has_edge(a, b):
            G.remove_edge(a, b)

G = nx.Graph()

async def save_graph_periodically():
    while True:
        net = Network(height='750px', width='100%', notebook=False)
        for node in G.nodes():
            node_str = node.hex() if isinstance(node, bytes) else str(node)
            net.add_node(node_str, label=node_str[:8])
        for edge in G.edges():
            a = edge[0].hex() if isinstance(edge[0], bytes) else str(edge[0])
            b = edge[1].hex() if isinstance(edge[1], bytes) else str(edge[1])
            net.add_edge(a, b)
        net.write_html('topology.html', notebook=False)  # Fix: Use write_html instead of show
        print("Topology updated and saved to topology.html")
        await asyncio.sleep(10)

async def start_peers(n=100):
    tasks = []
    for i in range(n):
        # Build per-peer config
        builder = ConfigBuilder().clear_keys().clear_overlays()
        builder.add_key("peer", "medium", f"key{i}.pem")
        builder.add_overlay("MyCommunity", "peer",
                            [WalkerDefinition(Strategy.RandomWalk, 10, {'timeout': 3.0})],
                            default_bootstrap_defs, {}, [('started',)])
        cfg = builder.finalize()
        # Start each IPv8 instance on its own port
        ipv8 = IPv8(cfg, extra_communities={"MyCommunity": MyCommunity})
        tasks.append(ipv8.start())
    tasks.append(save_graph_periodically())  # Add the graph-saving task

    await asyncio.gather(*tasks)
    await run_forever()

if __name__ == "__main__":
    run(start_peers())