import base64
import hashlib
import json
import time
import uuid
from asyncio import create_task, sleep
from typing import Dict, List, Set, Tuple
 
import lmdb
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from ipv8.community import Community, CommunitySettings
from ipv8.lazy_community import lazy_wrapper
from ipv8.types import Peer
 
from models.models import ChessTransaction, MoveData
from utils.utils import lottery_selection
 
 
class ChessCommunity(Community):
    """Community implementation for chess game transactions using IPv8."""
   
    community_id = b'chess_platform123456'
    INITIAL_STAKE = 120
 
    def __init__(self, settings: CommunitySettings) -> None:
        """Initialize the chess community."""
        super().__init__(settings)
        self.add_message_handler(ChessTransaction, self.on_transaction)
        self.add_message_handler(MoveData, self.on_move)
       
        # Set up databases
        self.db_env = lmdb.open('chess_db', max_dbs=3, map_size=10**8)
        self.tx_db = self.db_env.open_db(b'transactions')
        self.stake_db = self.db_env.open_db(b'stakes')
        self.moves_db = self.db_env.open_db(b'moves')
 
        # Initialize state
        self.transactions: Set[str] = set()
        self.mempool: List[ChessTransaction] = []
        self.sent: Set[Tuple[bytes, str]] = set()
        self.stakes: Dict[bytes, int] = {}
 
        # Load existing transactions and stakes
        with self.db_env.begin(db=self.tx_db) as tx:
            for key, _ in tx.cursor():
                self.transactions.add(key.decode())
        with self.db_env.begin(db=self.stake_db) as tx:
            for key, val in tx.cursor():
                self.stakes[key] = int(val.decode())
 
        # Generate keys for this peer
        self.sk = Ed25519PrivateKey.generate()
        self.pk = self.sk.public_key()
        self.pubkey_bytes = self.pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
       
        # Assign initial stake to this peer if it doesn't have any
        if self.pubkey_bytes not in self.stakes:
            self.stake_tokens(self.INITIAL_STAKE)
 
    def stake_tokens(self, amount: int) -> None:
        """Stake tokens in the system."""
        pid = self.pubkey_bytes
        new = self.stakes.get(pid, 0) + amount
        with self.db_env.begin(db=self.stake_db, write=True) as tx:
            tx.put(pid, str(new).encode())
        self.stakes[pid] = new
        print(f"Staked {amount}, total stake: {new}")
 
    def total_stake(self) -> int:
        """Calculate the total stake in the system."""
        return sum(self.stakes.values())
 
    def select_validators(self, seed: bytes, k: int) -> List[bytes]:
        """Select validators using lottery selection based on stake."""
        total = self.total_stake()
        sel = []
        for pid, stake in self.stakes.items():
            combined_seed = seed + pid
            if lottery_selection(combined_seed, stake, total):
                sel.append(pid)
                if len(sel) >= k: break
        return sel
 
    def select_proposer(self, seed: bytes) -> bytes:
        """Select a proposer for block creation."""
        vs = self.select_validators(seed, 1)
        return vs[0] if vs else None
 
    def started(self) -> None:
        """Called when the community is started."""
        self.network.add_peer_observer(self)
        create_task(self.periodic_broadcast())
        create_task(self.pos_round())
 
    def on_peer_added(self, peer: Peer) -> None:
        """Called when a new peer is added."""
        print("New peer:", peer)
 
    @lazy_wrapper(MoveData)
    def on_move(self, peer: Peer, payload: MoveData) -> None:
        """Handle incoming move messages."""
        key = f"{payload.match_id}:{payload.id}".encode()
        with self.db_env.begin(db=self.moves_db, write=True) as tx:
            if tx.get(key):
                print(f"Move {payload.id} for match {payload.match_id} already exists")
                return
            tx.put(key, json.dumps(payload.to_dict()).encode())
        print(f"Stored move {payload.id} for match {payload.match_id} from {peer}")
 
    @lazy_wrapper(ChessTransaction)
    def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
        """Handle incoming transactions with verification."""
        if payload.nonce in self.transactions:
            print(f"Transaction {payload.nonce} already processed")
            return
        if not payload.verify_signatures():
            print(f"Transaction {payload.nonce} failed verification")
            return
        with self.db_env.begin(db=self.tx_db, write=True) as tx:
            tx.put(payload.nonce.encode(), json.dumps(payload.to_dict()).encode())
        self.transactions.add(payload.nonce)
        self.mempool.append(payload)
        print(f"Accepted transaction {payload.nonce} from {peer}")
 
    def get_stored_transactions(self) -> List[ChessTransaction]:
        """Get all transactions stored in the database."""
        out = []
        required_keys = {"match_id", "winner", "player1_pubkey", "player1_signature",
                        "player2_pubkey", "player2_signature", "nonce", "tx_pubkey", "signature"}
        with self.db_env.begin(db=self.tx_db) as tx:
            for key, raw in tx.cursor():
                try:
                    data = json.loads(raw.decode())
                    if not all(key in data for key in required_keys):
                        print(f"Skipping invalid transaction {key.decode()}: missing required keys")
                        continue
                    out.append(ChessTransaction.from_dict(data))
                except Exception as e:
                    print(f"Error loading transaction {key.decode()}: {e}")
        return out
 
    def get_stored_moves(self, match_id: str) -> List[MoveData]:
        """Get all moves for a given match_id from the database."""
        out = []
        with self.db_env.begin(db=self.moves_db) as tx:
            cursor = tx.cursor()
            for key, raw in cursor:
                if key.decode().startswith(f"{match_id}:"):
                    try:
                        out.append(MoveData.from_dict(json.loads(raw.decode())))
                    except Exception as e:
                        print(f"Error loading move {key.decode()}: {e}")
        return sorted(out, key=lambda x: x.id)
 
    async def periodic_broadcast(self) -> None:
        """Periodically broadcast transactions to peers."""
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
        if not tx.verify_signatures():
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
 
    async def send_moves(self, match_id: str, moves: List[dict], p1_sk: Ed25519PrivateKey,
                        p2_sk: Ed25519PrivateKey, p1_pk: Ed25519PublicKey,
                        p2_pk: Ed25519PublicKey) -> ChessTransaction:
        """Send moves one by one with a 4-second delay and return the final transaction."""
        for move_def in moves:
            move_id = move_def["id"]
            player = move_def["player"]
            move_value = move_def["move_str"]
            move_data_to_sign = f"{move_id}:{player}:{move_value}".encode()
            sk = p1_sk if player == "player1" else p2_sk
            move_signature = base64.b64encode(sk.sign(move_data_to_sign)).decode()
           
            move_data = MoveData(
                id=move_id,
                player=player,
                move=move_value,
                signature=move_signature
            )
           
            # Store move locally
            key = f"{match_id}:{move_id}".encode()
            with self.db_env.begin(db=self.moves_db, write=True) as tx:
                tx.put(key, json.dumps(move_data.to_dict()).encode())
           
            # Send move to peers
            for p in self.get_peers():
                if p.mid != self.pubkey_bytes:
                    self.ez_send(p, move_data)
            print(f"Sent move {move_id} for match {match_id}")
           
            await sleep(4)  # 4-second delay
 
        # Create final transaction
        winner = moves[-1]["player"]
        outcome = f"{match_id}:{winner}".encode()
        p1_sig = base64.b64encode(p1_sk.sign(outcome)).decode()
        p2_sig = base64.b64encode(p2_sk.sign(outcome)).decode()
       
        p1_pk_str = base64.b64encode(
            p1_pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        ).decode()
        p2_pk_str = base64.b64encode(
            p2_pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        ).decode()
       
        nonce = match_id
        tx_data = f"{match_id}:{winner}:{nonce}".encode()
        tx_sig = base64.b64encode(self.sk.sign(tx_data)).decode()
        tx_pk_str = base64.b64encode(
            self.pk.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        ).decode()
 
        return ChessTransaction(
            match_id=match_id,
            winner=winner,
            player1_pubkey=p1_pk_str,
            player1_signature=p1_sig,
            player2_pubkey=p2_pk_str,
            player2_signature=p2_sig,
            nonce=nonce,
            tx_pubkey=tx_pk_str,
            signature=tx_sig
        )
 
    def generate_fake_match(self) -> None:
        """Generate a fake match and start sending moves."""
        mid = str(uuid.uuid4())
       
        # Simulate two players
        p1_sk = Ed25519PrivateKey.generate()
        p1_pk = p1_sk.public_key()
        p2_sk = Ed25519PrivateKey.generate()
        p2_pk = p2_sk.public_key()
 
        # Define the sequence of moves
        raw_move_definitions = [
            {"id": 1, "player": "player1", "move_str": "e4"},
            {"id": 2, "player": "player2", "move_str": "e5"},
            {"id": 3, "player": "player1", "move_str": "Nf3"}
        ]
       
        # Start sending moves and transaction
        create_task(self.send_moves(mid, raw_move_definitions, p1_sk, p2_sk, p1_pk, p2_pk))
 
    async def pos_round(self) -> None:
        """Run a proof of stake consensus round."""
        while True:
            seed = hashlib.sha256(str(time.time()).encode()).digest()
            proposer = self.select_proposer(seed)
           
            if proposer == self.pubkey_bytes and self.mempool:
                # Verify all transactions in mempool
                valid_txs = [tx for tx in self.mempool if tx.verify_signatures()]
               
                if valid_txs:
                    blk = [tx.to_dict() for tx in valid_txs]
                    blob = json.dumps(blk).encode()
                    psig = base64.b64encode(self.sk.sign(blob)).decode()
                    print(f"Proposed block ({len(blk)} tx): {psig[:8]}...")
                    self.mempool = [tx for tx in self.mempool if tx not in valid_txs]
                else:
                    print("No valid transactions to propose")
                   
            committee = self.select_validators(seed, 5)
            print("Committee:", [base64.b64encode(c)[:8].decode() for c in committee])
           
            await sleep(5)