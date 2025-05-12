# import ctypes
# import os

# libsodium_path = r"C:\Users\kerel\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\LocalCache\local-packages\Python311\site-packages\libnacl\libsodium.dll"
# if os.path.exists(libsodium_path):
#     try:
#         ctypes.WinDLL(libsodium_path)
#         print(f"[+] Successfully loaded libsodium.dll from {libsodium_path}")
#     except Exception as e:
#         print(f"[!] Failed to load libsodium.dll: {e}")
# else:
#     print(f"[!] Could not find libsodium.dll at {libsodium_path}")


import os
import secrets
import base64
import hashlib
import json
import socket
from asyncio import run, create_task, sleep
from dataclasses import dataclass
import time
from typing import Set, List, Tuple
import uuid
import lmdb
 
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
 
from ipv8.community import Community, CommunitySettings
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.payload_dataclass import DataClassPayload
from ipv8.types import Peer
from ipv8.util import run_forever
from ipv8_service import IPv8


# PoS VRF helper
def vrf_sortition(sk: Ed25519PrivateKey, seed: bytes, total_stake: int, my_stake: int) -> bool:
    sk_bytes = sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    h = hashlib.sha256(sk_bytes + seed).digest()
    return (int.from_bytes(h, 'big') % total_stake) < my_stake


@dataclass
class ChessTransaction(DataClassPayload[1]):
    match_id: str
    moves: str  # JSON-encoded list of Move objects
    winner: str
    winner_signature: str  # base64 encoded
    nonce: str
    pubkey: str  # base64 encoded
    signature: str
    start_signatures: str = "{}"

    def to_dict(self):
        return {
            "match_id": self.match_id,
            "start_signatures": json.loads(self.start_signatures),
            "moves": json.loads(self.moves),
            "winner": self.winner,
            "winner_signature": self.winner_signature,
            "nonce": self.nonce,
            "pubkey": self.pubkey,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data):
        moves_json = json.dumps(data["moves"])
        start_signatures_json = json.dumps(data.get("start_signatures", {}))
        return cls(
            match_id=data["match_id"],
            start_signatures=start_signatures_json,
            moves=moves_json,
            winner=data["winner"],
            winner_signature=data["winner_signature"],
            nonce=data["nonce"],
            pubkey=data["pubkey"],
            signature=data["signature"],
        )
    
class ChessCommunity(Community):
    community_id = b'chess_platform123456'
 
    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(ChessTransaction, self.on_transaction)
        self.db_env = lmdb.open('chess_transactions_db', max_dbs=1, map_size=104857600)
        self.db = self.db_env.open_db(b'transactions')
 
        self.transactions: Set[str] = set()
        self.mempool: List[ChessTransaction] = []
        self.sent: Set[Tuple[bytes, str]] = set()  # track (peer_id, tx_nonce)
 
        with self.db_env.begin(db=self.db, write=True) as txn:
            for key, _ in txn.cursor():
                self.transactions.add(key.decode())
 
        self.sk = Ed25519PrivateKey.generate()
        self.pk = self.sk.public_key()
        self.pubkey_bytes = self.pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self.pubkey_b64 = base64.b64encode(self.pubkey_bytes).decode()
    def stake_tokens(self, amount: int):
        pid = self.pubkey_bytes
        new = self.stakes.get(pid, 0) + amount
        with self.db_env.begin(db=self.stake_db, write=True) as tx:
            tx.put(pid, str(new).encode())
        self.stakes[pid] = new
        print(f"Staked {amount}, total stake: {new}")
        
    def total_stake(self) -> int:
        return sum(self.stakes.values())
    
    def select_validators(self, seed: bytes, k: int) -> List[bytes]:
        total = self.total_stake()
        sel = []
        for pid, stake in self.stakes.items():
            if vrf_sortition(self.sk, seed + pid, total, stake):
                sel.append(pid)
                if len(sel) >= k: break
        return sel

    def select_proposer(self, seed: bytes) -> bytes:
        vs = self.select_validators(seed, 1)
        return vs[0] if vs else None
    
    def started(self) -> None:
        self.network.add_peer_observer(self)
        create_task(self.periodic_broadcast())
 
    def on_peer_added(self, peer: Peer) -> None:
        print("New peer:", peer)
 
    @lazy_wrapper(ChessTransaction)
    def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
        # Verify signature
        pubkey_bytes = base64.b64decode(payload.pubkey)
        pubkey = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        sig = base64.b64decode(payload.signature)
        try:
            pubkey.verify(sig, payload.nonce.encode())
        except Exception:
            print(f"Bad signature from {peer}, dropping TX {payload.nonce}")
            return
 
        # Deduplicate
        if payload.nonce in self.transactions:
            return
 
        # Persist friend's transaction
        with self.db_env.begin(db=self.db, write=True) as txn:
            txn.put(payload.nonce.encode(), json.dumps(payload.to_dict()).encode())
        self.transactions.add(payload.nonce)
 
        # Add to mempool for gossip
        self.mempool.append(payload)
 
    def get_stored_transactions(self) -> List[ChessTransaction]:
        txs: List[ChessTransaction] = []
        with self.db_env.begin(db=self.db) as txn:
            for key, raw in txn.cursor():
                data = json.loads(raw.decode())
                txs.append(ChessTransaction.from_dict(data))
        return txs
 
    async def periodic_broadcast(self):
        while True:
            for tx in list(self.mempool):
                if not isinstance(tx, ChessTransaction):
                    continue
                for peer in self.get_peers():
                    if peer != self.my_peer:
                        peer_id = peer.mid
                        if (peer_id, tx.nonce) not in self.sent:
                            self.ez_send(peer, tx)
                            self.sent.add((peer_id, tx.nonce))
            await sleep(5.0)
 
    def send_transaction(self, tx: ChessTransaction):
        # ensure local storage and mempool
        if tx.nonce not in self.transactions:
            with self.db_env.begin(db=self.db, write=True) as txn:
                txn.put(tx.nonce.encode(), json.dumps(tx.to_dict()).encode())
            self.transactions.add(tx.nonce)
            self.mempool.append(tx)
 
        for peer in self.get_peers():
            if peer != self.my_peer:
                peer_id = peer.mid
                if (peer_id, tx.nonce) not in self.sent:
                    self.ez_send(peer, tx)
                    self.sent.add((peer_id, tx.nonce))
 
    def generate_fake_match(self):
        match_id = str(uuid.uuid4())
        p1, p2 = "alice", "bob"
        moves = [
            {"id": 1, "player": p1, "move": "e4", "signature": ""},
            {"id": 2, "player": p2, "move": "e5", "signature": ""}
        ]
        moves_json = json.dumps(moves)
        winner = p1
        sk = Ed25519PrivateKey.generate()
        pk = sk.public_key()
        pubkey_b64 = base64.b64encode(
            pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        ).decode()
        winner_sig = base64.b64encode(sk.sign(winner.encode())).decode()
        nonce = match_id
        tx_sig = base64.b64encode(sk.sign(nonce.encode())).decode()
        return ChessTransaction(match_id, moves_json, winner, winner_sig, nonce, pubkey_b64, tx_sig, "{}")

# Utility to check if port is free
def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            print(f"Port {port} is already in use. Please free the port or choose another.")
            return False

async def manual_send_loop(community: ChessCommunity):
    while True:
        cmd = input("Commands: show, send, showmempool, clearmempool > ").strip()
        if cmd == "show":
            print("Stored transactions in LMDB:")
            for tx in community.get_stored_transactions():
                print(f"  Nonce: {tx.nonce}, Match ID: {tx.match_id}, Winner: {tx.winner}")
        elif cmd == "send":
            tx = community.generate_fake_match()
            community.send_transaction(tx)
            print(f"Transaction {tx.nonce} generated and broadcasted.")
        elif cmd == "showmempool":
            print("Mempool:")
            for tx in community.mempool:
                print(f"  Nonce: {tx.nonce}, Match ID: {tx.match_id}")
        elif cmd == "clearmempool":
            community.mempool.clear()
            print("Mempool cleared.")
        await sleep(1)
 

async def start_communities(port=8000):
    if not check_port(port):
        raise RuntimeError(f"Cannot start peer on port {port}")
    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.set_port(port)
    builder.add_key("my peer", "medium", f"chess_peer_key.pem")
    builder.add_overlay(
        "ChessCommunity",
        "my peer",
        [WalkerDefinition(Strategy.RandomWalk, 10, {'timeout': 5.0})],
        default_bootstrap_defs,
        {},
        [('started',)]
    )
    ipv8 = IPv8(builder.finalize(), extra_communities={'ChessCommunity': ChessCommunity})
    await ipv8.start()
    community = ipv8.get_overlay(ChessCommunity)
    if not community:
        raise RuntimeError("ChessCommunity not found")
    print(f"Community initialized with peer: {community.my_peer}")
    # Start the manual send loop
    create_task(manual_send_loop(community))
    await run_forever()
 
if __name__ == "__main__":
    run(start_communities())