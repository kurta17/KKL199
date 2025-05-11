import os
import secrets
import base64
import hashlib
import json
import socket
from asyncio import run, create_task, sleep
from dataclasses import dataclass
import time
from typing import Set, List
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
 
# Utility to check if port is free
def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            print(f"Port {port} is already in use. Please free the port or choose another.")
            return False
 
 

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