# import ctypes
# import os

# # Manually load libsodium.dll
# libsodium_path = r"C:\Users\kerel\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\LocalCache\local-packages\Python311\site-packages\libnacl\libsodium.dll"
# if os.path.exists(libsodium_path):
#     try:
#         ctypes.WinDLL(libsodium_path)
#         print(f"[+] Successfully loaded libsodium.dll from {libsodium_path}")
#     except Exception as e:
#         print(f"[!] Failed to load libsodium.dll: {e}")
# else:
#     print(f"[!] Could not find libsodium.dll at {libsodium_path}")


import ctypes
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
from cryptography.exceptions import InvalidSignature

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
    moves: str  # JSON string of moves
    winner: str
    player1_pubkey: str  # Base64-encoded public key
    player1_signature: str  # Signature on match outcome
    player2_pubkey: str
    player2_signature: str
    nonce: str
    tx_pubkey: str  # Public key of transaction signer
    signature: str  # Signature on transaction

    def to_dict(self):
        return {
            "match_id": self.match_id,
            "moves": json.loads(self.moves),
            "winner": self.winner,
            "player1_pubkey": self.player1_pubkey,
            "player1_signature": self.player1_signature,
            "player2_pubkey": self.player2_pubkey,
            "player2_signature": self.player2_signature,
            "nonce": self.nonce,
            "tx_pubkey": self.tx_pubkey,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            match_id=data["match_id"],
            moves=json.dumps(data["moves"]),
            winner=data["winner"],
            player1_pubkey=data["player1_pubkey"],
            player1_signature=data["player1_signature"],
            player2_pubkey=data["player2_pubkey"],
            player2_signature=data["player2_signature"],
            nonce=data["nonce"],
            tx_pubkey=data["tx_pubkey"],
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

    def verify_match(self, tx: ChessTransaction) -> bool:
        """Verify the match moves, signatures, and winner."""
        try:
            # Decode public keys
            p1_pk_bytes = base64.b64decode(tx.player1_pubkey)
            p2_pk_bytes = base64.b64decode(tx.player2_pubkey)
            tx_pk_bytes = base64.b64decode(tx.tx_pubkey)
            p1_pk = Ed25519PublicKey.from_public_bytes(p1_pk_bytes)
            p2_pk = Ed25519PublicKey.from_public_bytes(p2_pk_bytes)
            tx_pk = Ed25519PublicKey.from_public_bytes(tx_pk_bytes)

            # Parse moves
            moves = json.loads(tx.moves)
            if not moves:
                print(f"Invalid transaction {tx.nonce}: Empty move list")
                return False

            # Verify move signatures and alternation
            for i, move in enumerate(moves):
                player = move["player"]
                move_str = move["move"]
                sig = base64.b64decode(move["signature"])
                move_data = f"{move['id']}:{player}:{move_str}".encode()
                pk = p1_pk if player == "player1" else p2_pk
                try:
                    pk.verify(sig, move_data)
                except InvalidSignature:
                    print(f"Invalid move signature for move {move['id']}")
                    return False
                # Check alternation
                expected_player = "player1" if i % 2 == 0 else "player2"
                if player != expected_player:
                    print(f"Invalid move order at move {move['id']}")
                    return False

            # Verify winner is the last move's player
            last_move = moves[-1]
            if last_move["player"] != tx.winner:
                print(f"Invalid winner: {tx.winner} does not match last move by {last_move['player']}")
                return False

            # Verify player signatures on match outcome
            outcome = f"{tx.match_id}:{tx.winner}:{tx.moves}".encode()
            try:
                p1_pk.verify(base64.b64decode(tx.player1_signature), outcome)
                p2_pk.verify(base64.b64decode(tx.player2_signature), outcome)
            except InvalidSignature:
                print(f"Invalid player signature for match {tx.match_id}")
                return False

            # Verify transaction signature
            tx_data = f"{tx.match_id}:{tx.moves}:{tx.winner}:{tx.nonce}".encode()
            try:
                tx_pk.verify(base64.b64decode(tx.signature), tx_data)
            except InvalidSignature:
                print(f"Invalid transaction signature for {tx.nonce}")
                return False

            return True
        except Exception as e:
            print(f"Error verifying transaction {tx.nonce}: {e}")
            return False

    @lazy_wrapper(ChessTransaction)
    def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
        """Handle incoming transactions with verification."""
        if payload.nonce in self.transactions:
            print(f"Transaction {payload.nonce} already processed")
            return
        if not self.verify_match(payload):
            print(f"Transaction {payload.nonce} failed verification")
            return
        with self.db_env.begin(db=self.tx_db, write=True) as tx:
            tx.put(payload.nonce.encode(), json.dumps(payload.to_dict()).encode())
        self.transactions.add(payload.nonce)
        self.mempool.append(payload)
        print(f"Accepted transaction {payload.nonce} from {peer}")

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
        """Send a verified transaction to peers."""
        if tx.nonce in self.transactions:
            print(f"Transaction {tx.nonce} already exists")
            return
        if not self.verify_match(tx):
            print(f"Transaction {tx.nonce} failed verification")
            return
        with self.db_env.begin(db=self.tx_db, write=True) as wr:
            wr.put(tx.nonce.encode(), json.dumps(tx.to_dict()).encode())
        self.transactions.add(tx.nonce)
        self.mempool.append(tx)
        for p in self.get_peers():
            if p.mid != self.pubkey_bytes and (p.mid, tx.nonce) not in self.sent:
                self.ez_send(p, tx)
                self.sent.add((p.mid, tx.nonce))
        print(f"Sent transaction {tx.nonce}")

    def generate_fake_match(self) -> ChessTransaction:
        """Generate a fake match with two players signing the outcome."""
        mid = str(uuid.uuid4())
        # Simulate two players
        p1_sk = Ed25519PrivateKey.generate()
        p1_pk = p1_sk.public_key()
        p2_sk = Ed25519PrivateKey.generate()
        p2_pk = p2_sk.public_key()

        moves = [
            {"id": 1, "player": "player1", "move": "e4", "signature": ""},
            {"id": 2, "player": "player2", "move": "e5", "signature": ""},
            {"id": 3, "player": "player1", "move": "Nf3", "signature": ""}
        ]
        # Sign each move
        for move in moves:
            move_data = f"{move['id']}:{move['player']}:{move['move']}".encode()
            sk = p1_sk if move["player"] == "player1" else p2_sk
            move["signature"] = base64.b64encode(sk.sign(move_data)).decode()

        mv_str = json.dumps(moves)
        winner = moves[-1]["player"]  # Last move's player wins
        outcome = f"{mid}:{winner}:{mv_str}".encode()
        p1_sig = base64.b64encode(p1_sk.sign(outcome)).decode()
        p2_sig = base64.b64encode(p2_sk.sign(outcome)).decode()

        p1_pk_str = base64.b64encode(
            p1_pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        ).decode()
        p2_pk_str = base64.b64encode(
            p2_pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        ).decode()

        nonce = mid
        tx_data = f"{mid}:{mv_str}:{winner}:{nonce}".encode()
        tx_sig = base64.b64encode(self.sk.sign(tx_data)).decode()
        tx_pk_str = base64.b64encode(
            self.pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        ).decode()

        return ChessTransaction(
            match_id=mid,
            moves=mv_str,
            winner=winner,
            player1_pubkey=p1_pk_str,
            player1_signature=p1_sig,
            player2_pubkey=p2_pk_str,
            player2_signature=p2_sig,
            nonce=nonce,
            tx_pubkey=tx_pk_str,
            signature=tx_sig
        )

    async def pos_round(self) -> None:
        while True:
            seed = hashlib.sha256(str(time.time()).encode()).digest()
            proposer = self.select_proposer(seed)
            if proposer == self.pubkey_bytes and self.mempool:
                # Verify all transactions in mempool
                valid_txs = [tx for tx in self.mempool if self.verify_match(tx)]
                if valid_txs:
                    blk = [tx.to_dict() for tx in valid_txs]
                    blob = json.dumps(blk).encode()
                    psig = base64.b64encode(self.enveloppe.sign(blob)).decode()
                    print(f"Proposed block ({len(blk)} tx): {psig[:8]}...")
                    self.mempool = [tx for tx in self.mempool if tx not in valid_txs]
                else:
                    print("No valid transactions to propose")
            committee = self.select_validators(seed, 5)
            print("Committee:", [base64.b64encode(c)[:8].decode() for c in committee])
            await sleep(50)

async def manual_send_loop(comm: ChessCommunity) -> None:
    while True:
        cmd = input("Commands: stake <amt>, show, send, showmempool, clearmempool, showstakes > ").split()
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
        elif cmd[0] == "showmempool":
            print("Mempool size:", len(comm.mempool))
        elif cmd[0] == "clearmempool":
            comm.mempool.clear()
        elif cmd[0] == "showstakes":
            print("Stakes:", {base64.b64encode(k)[:8].decode(): v for k, v in comm.stakes.items()})
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