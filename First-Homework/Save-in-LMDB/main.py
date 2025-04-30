import os
import secrets
import base64
from asyncio import run, create_task, sleep
from dataclasses import dataclass
from typing import Set
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

@dataclass
class Transaction(DataClassPayload[1]):
    nonce: str
    pubkey: str  # base64 encoded
    signature: str  # base64 encoded

class MyCommunity(Community):
    community_id = b'harbourspacegeogangs'

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(Transaction, self.on_transaction)
        # Initialize LMDB database
        self.db_env = lmdb.open('transactions_db', max_dbs=1, map_size=10485760)  # 10MB
        self.db = self.db_env.open_db(b'transactions')
        self.transactions: Set[str] = set()  # In-memory cache for quick checks
        # Load existing transactions from LMDB into memory
        with self.db_env.begin(db=self.db) as txn:
            cursor = txn.cursor()
            for key, _ in cursor:
                self.transactions.add(key.decode())
        # Generate keypair
        self.sk = Ed25519PrivateKey.generate()
        self.pk = self.sk.public_key()
        self.pubkey_bytes = self.pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self.pubkey_b64 = base64.b64encode(self.pubkey_bytes).decode()

    def started(self) -> None:
        print(f"My peer started: {self.my_peer}")
        create_task(self.periodic_broadcast())

    async def periodic_broadcast(self):
        while True:
            nonce = secrets.token_hex(16)
            signature = self.sk.sign(nonce.encode())
            tx = Transaction(
                nonce=nonce,
                pubkey=self.pubkey_b64,
                signature=base64.b64encode(signature).decode()
            )
            for peer in self.get_peers():
                if peer != self.my_peer:
                    self.ez_send(peer, tx)
                    print(f"Broadcasted tx nonce={nonce} to {peer}")
            await sleep(10)  # Send every 10 seconds

    @lazy_wrapper(Transaction)
    def on_transaction(self, peer: Peer, payload: Transaction) -> None:
        try:
            pubkey_bytes = base64.b64decode(payload.pubkey)
            signature_bytes = base64.b64decode(payload.signature)
            pubkey = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
            pubkey.verify(signature_bytes, payload.nonce.encode())
            # Store in LMDB and in-memory set
            if payload.nonce not in self.transactions:
                with self.db_env.begin(db=self.db, write=True) as txn:
                    txn.put(payload.nonce.encode(), payload.pubkey.encode())
                self.transactions.add(payload.nonce)
                print(f"Valid transaction from {peer}: nonce={payload.nonce}")
            else:
                print(f"Duplicate transaction from {peer}: nonce={payload.nonce}")
        except Exception as e:
            print(f"Invalid transaction from {peer}: {e}")

async def manual_send_loop(community: MyCommunity):
    while True:
        cmd = input("Type 'show' to list transactions, Enter to continue: ").strip()
        if cmd == "show":
            print("Stored transactions:")
            for tx in community.transactions:
                print(tx)
        await sleep(1)

async def start_communities():
    builder = ConfigBuilder().clear_keys().clear_overlays()
    # Specify a file path for the keypair (generated if it doesn't exist)
    builder.add_key("my peer", "medium", "peer_key.pem")
    builder.add_overlay("MyCommunity", "my peer",
                        [WalkerDefinition(Strategy.RandomWalk, 10, {'timeout': 3.0})],
                        default_bootstrap_defs, {}, [('started',)])
    ipv8 = IPv8(builder.finalize(), extra_communities={'MyCommunity': MyCommunity})
    await ipv8.start()
    community = ipv8.overlays[0]
    create_task(manual_send_loop(community))
    await run_forever()

if __name__ == "__main__":
    run(start_communities())