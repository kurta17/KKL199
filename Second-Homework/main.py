import os
import secrets
import base64
import time
from asyncio import run, create_task, sleep
from dataclasses import dataclass
from typing import Set
import lmdb
import random
import logging
import networkx as nx
from pyvis.network import Network

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

from ipv8.community import Community, CommunitySettings
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs, Bootstrapper
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.payload_dataclass import DataClassPayload
from ipv8.messaging.payload import VariablePayloadWID
from ipv8.messaging.serialization import default_serializer
from ipv8.types import Peer
from ipv8.util import run_forever
from ipv8_service import IPv8

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Define unique message IDs
MSG_TRANSACTION = 1
MSG_REQUEST_TRANSACTIONS = 2
MSG_TRANSACTIONS_RESPONSE = 3

@dataclass
class Transaction(DataClassPayload[MSG_TRANSACTION]):
    format_list = ['varlenH', 'varlenH', 'varlenH']
    names = ['nonce', 'pubkey', 'signature']
    nonce: str
    pubkey: str  # base64 encoded
    signature: str  # base64 encoded

    @classmethod
    def from_unpack_list(cls, *args):
        if len(args) == 0:
            return cls(nonce="", pubkey="", signature="")
        if len(args) != 3:
            raise ValueError(f"Expected 3 arguments (nonce, pubkey, signature), got {len(args)}: {args}")
        return cls(*args)

@dataclass
class RequestTransactions(DataClassPayload[MSG_REQUEST_TRANSACTIONS]):
    pass

class TransactionsResponse(VariablePayloadWID):
    msg_id = MSG_TRANSACTIONS_RESPONSE
    format_list = ['varlenH']  # Variable-length string for transactions
    names = ['transactions']

    @staticmethod
    def pack(transactions: str) -> bytes:
        return default_serializer.pack('varlenH', transactions.encode('utf-8'))

    @staticmethod
    def unpack(data: bytes, offset: int) -> tuple[str, int]:
        transactions, offset = default_serializer.unpack('varlenH', data, offset)
        return transactions.decode('utf-8'), offset

# Network topology graph
G = nx.Graph()

class MyCommunity(Community):
    community_id = b'harbour_communityid2'
    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.network.add_peer_observer(self)
        self.add_message_handler(MSG_TRANSACTION, self.on_transaction)
        self.add_message_handler(MSG_REQUEST_TRANSACTIONS, self.on_request_transactions)
        self.add_message_handler(MSG_TRANSACTIONS_RESPONSE, self.on_transactions_response)
        port = self.my_peer.address[1] if self.my_peer else os.getpid()
        self.db_env = lmdb.open(f'transactions_db_{port}', max_dbs=1, map_size=10485760, max_readers=2048)
        self.db = self.db_env.open_db(b'transactions')
        self.transactions: Set[str] = set()
        self.recently_processed: Set[str] = set()
        self._load_transactions()
        self.sk = Ed25519PrivateKey.generate()
        self.pk = self.sk.public_key()
        self.pubkey_bytes = self.pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self.pubkey_b64 = base64.b64encode(self.pubkey_bytes).decode()
        self.sent_messages = 0
        self.duplicate_received = 0
        self.push_probability = 0.7
        self.fanout = 3

    def _load_transactions(self):
        for attempt in range(3):
            try:
                with self.db_env.begin(db=self.db) as txn:
                    cursor = txn.cursor()
                    for key, _ in cursor:
                        self.transactions.add(key.decode())
                break
            except lmdb.ReadersFullError:
                logger.warning(f"ReadersFullError on load attempt {attempt + 1}, retrying...")
                time.sleep(0.1 * (attempt + 1))
        else:
            logger.error("Failed to load transactions after retries due to ReadersFullError")

    def ez_send(self, peer, msg):
        super().ez_send(peer, msg)
        self.sent_messages += 1

    def started(self) -> None:
        print(f"My peer started: {self.my_peer}")
        nonce = secrets.token_hex(16)
        signature = self.sk.sign(nonce.encode())
        signature_b64 = base64.b64encode(signature).decode()
        with self.db_env.begin(db=self.db, write=True) as txn:
            value = f"{self.pubkey_b64}|{signature_b64}".encode()
            txn.put(nonce.encode(), value)
        self.transactions.add(nonce)
        print(f"Added initial transaction: nonce={nonce}")
        create_task(self.push_transaction(nonce, self.pubkey_b64, signature_b64))
        create_task(self.periodic_pull())
        create_task(self.periodic_push())
        create_task(self.log_topology())
        create_task(self.log_stats())

    async def periodic_pull(self):
        while True:
            peers = self.get_peers()
            if peers:
                random_peer = random.choice(peers)
                self.ez_send(random_peer, RequestTransactions())
                print(f"[PULL] Requested transactions from {random_peer}")
            await sleep(10)

    async def periodic_push(self):
        while True:
            await sleep(15)
            peers = self.get_peers()
            if not peers or not self.transactions:
                continue
            tx_to_push = random.choice(list(self.transactions))
            for attempt in range(3):
                try:
                    with self.db_env.begin(db=self.db) as txn:
                        value = txn.get(tx_to_push.encode())
                        if value:
                            pubkey_b64, signature_b64 = value.decode().split("|")
                            selected_peers = random.sample(peers, min(self.fanout, len(peers)))
                            for peer in selected_peers:
                                tx = Transaction(nonce=tx_to_push, pubkey=pubkey_b64, signature=signature_b64)
                                self.ez_send(peer, tx)
                                print(f"[PUSH] Pushed transaction {tx_to_push[:8]}... to {peer}")
                    break
                except lmdb.ReadersFullError:
                    logger.warning(f"ReadersFullError in periodic_push, attempt {attempt + 1}, retrying...")
                    await sleep(0.1 * (attempt + 1))
            else:
                logger.error(f"Failed to push transaction {tx_to_push[:8]}... after retries")

    async def push_transaction(self, nonce, pubkey_b64, signature_b64):
        peers = self.get_peers()
        if not peers or random.random() > self.push_probability:
            print(f"[PUSH] Skipping push for transaction {nonce[:8]}... based on probability")
            return
        selected_peers = random.sample(peers, min(self.fanout, len(peers)))
        for peer in selected_peers:
            tx = Transaction(nonce=nonce, pubkey=pubkey_b64, signature=signature_b64)
            self.ez_send(peer, tx)
            print(f"[PUSH] Pushed new transaction {nonce[:8]}... to {peer}")

    async def log_stats(self):
        while True:
            await sleep(60)
            with open(f"stats_{self.my_peer.address[1]}.txt", "a") as f:
                f.write(f"{time.time()}: sent_messages={self.sent_messages}, duplicate_received={self.duplicate_received}\n")

    @lazy_wrapper(RequestTransactions)
    def on_request_transactions(self, peer: Peer, payload: RequestTransactions) -> None:
        for attempt in range(3):
            try:
                with self.db_env.begin(db=self.db) as txn:
                    cursor = txn.cursor()
                    serialized_transactions = []
                    for key, value in cursor:
                        nonce = key.decode()
                        pubkey_b64, signature_b64 = value.decode().split("|")
                        serialized_tx = f"{nonce}|{pubkey_b64}|{signature_b64}"
                        serialized_transactions.append(serialized_tx)
                transactions_str = ";".join(serialized_transactions) if serialized_transactions else ""
                packed_transactions = TransactionsResponse.pack(transactions_str)
                self.ez_send(peer, TransactionsResponse(transactions=packed_transactions))
                print(f"[PULL-RESPONSE] Sent {len(serialized_transactions)} transactions to {peer}")
                break
            except lmdb.ReadersFullError:
                logger.warning(f"ReadersFullError in on_request_transactions, attempt {attempt + 1}, retrying...")
                time.sleep(0.1 * (attempt + 1))
        else:
            logger.error(f"Failed to send transactions to {peer} after retries due to ReadersFullError")

    @lazy_wrapper(TransactionsResponse)
    def on_transactions_response(self, peer: Peer, payload: TransactionsResponse) -> None:
        transactions_str, _ = TransactionsResponse.unpack(payload.transactions, 0)
        serialized_transactions = transactions_str.split(";") if transactions_str else []
        new_transactions = 0
        for serialized_tx in serialized_transactions:
            try:
                nonce, pubkey_b64, signature_b64 = serialized_tx.split("|")
                tx = Transaction(nonce=nonce, pubkey=pubkey_b64, signature=signature_b64)
                pubkey_bytes = base64.b64decode(tx.pubkey)
                signature_bytes = base64.b64decode(tx.signature)
                pubkey = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
                pubkey.verify(signature_bytes, tx.nonce.encode())
                if tx.nonce not in self.transactions:
                    with self.db_env.begin(db=self.db, write=True) as txn:
                        value = f"{tx.pubkey}|{tx.signature}".encode()
                        txn.put(tx.nonce.encode(), value)
                    self.transactions.add(tx.nonce)
                    new_transactions += 1
                    if random.random() < self.push_probability:
                        create_task(self.push_transaction(tx.nonce, tx.pubkey, tx.signature))
                else:
                    self.duplicate_received += 1
            except Exception as e:
                print(f"Invalid transaction from {peer}: {e}")
        print(f"[PULL-RESPONSE] Received {new_transactions} new and {len(serialized_transactions) - new_transactions} duplicate transactions from {peer}")

    @lazy_wrapper(Transaction)
    def on_transaction(self, peer: Peer, payload: Transaction) -> None:
        try:
            pubkey_bytes = base64.b64decode(payload.pubkey)
            signature_bytes = base64.b64decode(payload.signature)
            pubkey = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
            pubkey.verify(signature_bytes, payload.nonce.encode())
            if payload.nonce not in self.transactions:
                with self.db_env.begin(db=self.db, write=True) as txn:
                    value = f"{payload.pubkey}|{payload.signature}".encode()
                    txn.put(payload.nonce.encode(), value)
                self.transactions.add(payload.nonce)
                print(f"[PUSH] Received valid new transaction from {peer}: nonce={payload.nonce[:8]}...")
                if random.random() < self.push_probability * 0.8:
                    create_task(self.push_transaction(payload.nonce, payload.pubkey, payload.signature))
            else:
                self.duplicate_received += 1
                print(f"[PUSH] Received duplicate transaction from {peer}: nonce={payload.nonce[:8]}...")
        except Exception as e:
            print(f"Invalid transaction from {peer}: {e}")

    async def log_topology(self):
        while True:
            peers = self.get_peers()
            # Log as ip:port for easier analysis and visualization
            peer_addresses = ','.join([f"{p.address[0]}:{p.address[1]}" for p in peers])
            with open(f"topology_{self.my_peer.address[1]}.txt", "a") as f:
                f.write(f"{time.time()}: {peer_addresses}\n")
            await sleep(30)

    def on_peer_added(self, peer):
        a = self.my_peer.mid.hex()
        b = peer.mid.hex()
        G.add_edge(a, b)

    def on_peer_removed(self, peer):
        a = self.my_peer.mid.hex()
        b = peer.mid.hex()
        if G.has_edge(a, b):
            G.remove_edge(a, b)

    def unload(self):
        print(f"Peer {self.my_peer.address[1]}: sent_messages={self.sent_messages}, duplicate_received={self.duplicate_received}")
        with open("output.txt", "a") as f:
            f.write(f"Peer {self.my_peer.address[1]}: sent_messages={self.sent_messages}, duplicate_received={self.duplicate_received}\n")
        super().unload()

class SparseCommunity(MyCommunity):
    max_peers = 5

class DenseCommunity(MyCommunity):
    max_peers = 100

async def manual_send_loop(community: MyCommunity):
    while True:
        cmd = input("Type 'show' to list transactions, Enter to continue: ").strip()
        if cmd == "show":
            print("Stored transactions (from LMDB):")
            with community.db_env.begin(db=community.db) as txn:
                cursor = txn.cursor()
                for key, value in cursor:
                    nonce = key.decode()
                    pubkey = value.decode().split("|")[0]
                    print(f"Nonce: {nonce}, Pubkey: {pubkey}")
        await sleep(1)

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
        net.write_html('topology.html', notebook=False)
        print("Topology updated and saved to topology.html")
        await sleep(10)

async def start_communities():
    builder = ConfigBuilder().clear_keys().clear_overlays()
    port = int(os.environ.get('IPV8_PORT', 0))
    builder.set_port(port)
    builder.add_key("my peer", "medium", f"peer_key_{os.getpid()}.pem")
    community_type = os.environ.get('COMMUNITY_TYPE', 'DenseCommunity')
    # Use default_bootstrap_defs for robust local peer discovery
    builder.add_overlay(community_type, "my peer",
                        [WalkerDefinition(Strategy.RandomWalk, 20, {'timeout': 3.0})],
                        default_bootstrap_defs,
                        {}, [('started',)])
    ipv8 = IPv8(builder.finalize(), extra_communities={
        'SparseCommunity': SparseCommunity,
        'DenseCommunity': DenseCommunity
    })
    await ipv8.start()
    community = ipv8.overlays[0]
    if os.environ.get('INTERACTIVE_MODE') == '1':
        create_task(manual_send_loop(community))
    create_task(save_graph_periodically())
    await run_forever()

if __name__ == "__main__":
    run(start_communities())