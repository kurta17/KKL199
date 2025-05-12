import os
import base64
import hashlib
import json
import socket
from asyncio import run, create_task, sleep
from dataclasses import dataclass
import time
from typing import Set, List, Tuple, Dict
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

# Utility to check port
def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            print(f"Port {port} is in use; cannot bind.")
            return False

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
    moves: str
    winner: str
    winner_signature: str
    nonce: str
    pubkey: str
    signature: str

    def to_dict(self):
        return {
            "match_id": self.match_id,
            "moves": json.loads(self.moves),
            "winner": self.winner,
            "winner_signature": self.winner_signature,
            "nonce": self.nonce,
            "pubkey": self.pubkey,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            match_id=data["match_id"],
            moves=json.dumps(data["moves"]),
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
        self.db_env = lmdb.open('chess_db', max_dbs=2, map_size=10**8)
        self.tx_db = self.db_env.open_db(b'transactions')
        self.stake_db = self.db_env.open_db(b'stakes')

        self.transactions: Set[str] = set()
        self.mempool: List[ChessTransaction] = []
        self.sent: Set[Tuple[bytes, str]] = set()
        self.stakes: Dict[bytes, int] = {}

        with self.db_env.begin(db=self.tx_db) as tx:
            for key, _ in tx.cursor(): self.transactions.add(key.decode())
        with self.db_env.begin(db=self.stake_db) as tx:
            for key, val in tx.cursor(): self.stakes[key] = int(val.decode())

        self.sk = Ed25519PrivateKey.generate()
        self.pk = self.sk.public_key()
        self.pubkey_bytes = self.pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )

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
        create_task(self.pos_round())

    def on_peer_added(self, peer: Peer) -> None:
        print("New peer:", peer)

    @lazy_wrapper(ChessTransaction)
    def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
        if payload.nonce in self.transactions: return
        with self.db_env.begin(db=self.tx_db, write=True) as tx:
            tx.put(payload.nonce.encode(), json.dumps(payload.to_dict()).encode())
        self.transactions.add(payload.nonce)
        self.mempool.append(payload)

    def get_stored_transactions(self) -> List[ChessTransaction]:
        out = []
        with self.db_env.begin(db=self.tx_db) as tx:
            for _, raw in tx.cursor():
                out.append(ChessTransaction.from_dict(json.loads(raw.decode())))
        return out
    
    
    async def periodic_broadcast(self):
        while True:
            for tx in list(self.mempool):
                for p in self.get_peers():
                    if p.mid != self.pubkey_bytes and (p.mid, tx.nonce) not in self.sent:
                        self.ez_send(p, tx)
                        self.sent.add((p.mid, tx.nonce))
            await sleep(5)

    def send_transaction(self, tx: ChessTransaction) -> None:
        if tx.nonce not in self.transactions:
            with self.db_env.begin(db=self.tx_db, write=True) as wr:
                wr.put(tx.nonce.encode(), json.dumps(tx.to_dict()).encode())
            self.transactions.add(tx.nonce)
            self.mempool.append(tx)
        for p in self.get_peers():
            if p.mid != self.pubkey_bytes and (p.mid, tx.nonce) not in self.sent:
                self.ez_send(p, tx)
                self.sent.add((p.mid, tx.nonce))

    def generate_fake_match(self) -> ChessTransaction:
        mid = str(uuid.uuid4())
        moves = [
            {"id":1, "player":"alice", "move":"e4", "signature":""},
            {"id":2, "player":"bob",   "move":"e5", "signature":""}
        ]
        mv_str = json.dumps(moves)
        sk = Ed25519PrivateKey.generate()
        pb = base64.b64encode(
            sk.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
        ).decode()
        win = "alice"
        ws = base64.b64encode(sk.sign(win.encode())).decode()
        nonce = mid
        sig_nonce = base64.b64encode(sk.sign(nonce.encode())).decode()
        return ChessTransaction(mid, mv_str, win, ws, nonce, pb, sig_nonce)

    async def pos_round(self) -> None:
        while True:
            seed = hashlib.sha256(str(time.time()).encode()).digest()
            proposer = self.select_proposer(seed)
            if proposer == self.pubkey_bytes and self.mempool:
                blk = [tx.to_dict() for tx in self.mempool]
                blob = json.dumps(blk).encode()
                psig = base64.b64encode(self.sk.sign(blob)).decode()
                print(f"Proposed block ({len(blk)} tx): {psig[:8]}...")
                self.mempool.clear()
            committee = self.select_validators(seed, 5)
            print("Committee:", [base64.b64encode(c)[:8].decode() for c in committee])
            await sleep(50)

async def manual_send_loop(comm: ChessCommunity) -> None:
    while True:
        cmd = input("Commands: stake <amt>, show, send, showmempool, clearmempool > ").split()
        if not cmd: continue
        if cmd[0] == "stake" and len(cmd) == 2:
            comm.stake_tokens(int(cmd[1]))
        elif cmd[0] == "show":
            for t in comm.get_stored_transactions():
                print(f"{t.nonce}: winner={t.winner}")
            for peer in comm.get_peers():
                print(f"Peer: {peer}")
        elif cmd[0] == "send":
            tx = comm.generate_fake_match()
            comm.send_transaction(tx)
            print(f"Sent {tx.nonce}")
        elif cmd[0] == "showmempool":
            print("Mempool size:", len(comm.mempool))
        elif cmd[0] == "clearmempool":
            comm.mempool.clear()
        await sleep(1)

async def start_communities(port: int = 8000) -> None:
    if not check_port(port):
        raise RuntimeError("Port bind failed")
    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.set_port(port)
    builder.add_key("my peer", "medium", "chess_peer_key.pem")
    builder.add_overlay(
        "ChessCommunity", "my peer",
        [WalkerDefinition(Strategy.RandomWalk, 5, {"timeout": 5.0})],
        default_bootstrap_defs,
        {},
        [('started',)]
    )
    ipv8 = IPv8(builder.finalize(), extra_communities={'ChessCommunity': ChessCommunity})
    await ipv8.start()
    comm = ipv8.get_overlay(ChessCommunity)
    print(f"Initialized: {comm.my_peer}")
    create_task(manual_send_loop(comm))
    await run_forever()

if __name__ == "__main__":
    run(start_communities())