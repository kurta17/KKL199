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

# Update imports for direct running from ChessChain directory
from models.models import ChessTransaction
from utils.utils import vrf_sortition


class ChessCommunity(Community):
    """Community implementation for chess game transactions using IPv8."""
    
    community_id = b'chess_platform123456'
    INITIAL_STAKE = 120

    def __init__(self, settings: CommunitySettings) -> None:
        """Initialize the chess community."""
        super().__init__(settings)
        self.add_message_handler(ChessTransaction, self.on_transaction)
        
        # Set up databases
        self.db_env = lmdb.open('chess_db', max_dbs=2, map_size=10**8)
        self.tx_db = self.db_env.open_db(b'transactions')
        self.stake_db = self.db_env.open_db(b'stakes')

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
        """Stake tokens in the system.
        
        Args:
            amount: Number of tokens to stake
        """
        pid = self.pubkey_bytes
        new = self.stakes.get(pid, 0) + amount
        with self.db_env.begin(db=self.stake_db, write=True) as tx:
            tx.put(pid, str(new).encode())
        self.stakes[pid] = new
        print(f"Staked {amount}, total stake: {new}")

    def total_stake(self) -> int:
        """Calculate the total stake in the system.
        
        Returns:
            int: Total stake amount
        """
        return sum(self.stakes.values())

    def select_validators(self, seed: bytes, k: int) -> List[bytes]:
        """Select validators using VRF sortition.
        
        Args:
            seed: Random seed for the sortition
            k: Number of validators to select
            
        Returns:
            List[bytes]: List of selected validator public keys
        """
        total = self.total_stake()
        sel = []
        for pid, stake in self.stakes.items():
            if vrf_sortition(self.sk, seed + pid, total, stake):
                sel.append(pid)
                if len(sel) >= k: break
        return sel

    def select_proposer(self, seed: bytes) -> bytes:
        """Select a proposer for block creation.
        
        Args:
            seed: Random seed for the selection
            
        Returns:
            bytes: Public key of the selected proposer, or None
        """
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

    @lazy_wrapper(ChessTransaction)
    def on_transaction(self, peer: Peer, payload: ChessTransaction) -> None:
        """Handle incoming transactions with verification.
        
        Args:
            peer: The peer that sent the transaction
            payload: The transaction payload
        """
        if payload.nonce in self.transactions:
            print(f"Transaction {payload.nonce} already processed")
            return
            
        if not payload.verify_signatures():
            print(f"Transaction {payload.nonce} failed verification")
            return
            
        # Use JSON serialization instead of pack_low
        with self.db_env.begin(db=self.tx_db, write=True) as tx:
            tx.put(payload.nonce.encode(), json.dumps(payload.to_dict()).encode())
            
        self.transactions.add(payload.nonce)
        self.mempool.append(payload)
        print(f"Accepted transaction {payload.nonce} from {peer}")

    def get_stored_transactions(self) -> List[ChessTransaction]:
        """Get all transactions stored in the database.
        
        Returns:
            List[ChessTransaction]: List of stored transactions
        """
        out = []
        with self.db_env.begin(db=self.tx_db) as tx:
            for _, raw in tx.cursor():
                # Use JSON deserialization instead of unpack_low
                out.append(ChessTransaction.from_dict(json.loads(raw.decode())))
        return out

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
        """Send a verified transaction to peers.
        
        Args:
            tx: The transaction to send
        """
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

    def generate_fake_match(self) -> ChessTransaction:
        """Generate a fake match with two players signing the outcome.
        
        Returns:
            ChessTransaction: A simulated chess match transaction
        """
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
            
            await sleep(50)