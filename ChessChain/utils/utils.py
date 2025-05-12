import hashlib
import socket
from typing import List

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def check_port(port: int) -> bool:
    """Check if a port is available for binding.
    
    Args:
        port: The port number to check
        
    Returns:
        bool: True if the port is available, False otherwise
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            print(f"Port {port} is in use; cannot bind.")
            return False


def vrf_sortition(sk: Ed25519PrivateKey, seed: bytes, total_stake: int, my_stake: int) -> bool:
    """Proof of stake verifiable random function (VRF) for validator selection.
    
    Args:
        sk: Private key of the participant
        seed: Random seed for the sortition
        total_stake: Total stake in the system
        my_stake: Stake of the participant
        
    Returns:
        bool: True if the participant is selected, False otherwise
    """
    sk_bytes = sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    h = hashlib.sha256(sk_bytes + seed).digest()
    return (int.from_bytes(h, 'big') % total_stake) < my_stake