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


def lottery_selection(seed: bytes, p_id: bytes, total_stake: int, peers: List[str]) -> bool:
    """Lottery-based random selection based on stake.
    
    Args:
        seed: The round seed
        p_id: Participant ID (public key bytes)
        total_stake: Total stake in the system
        peers: List of peer IDs to compare against
        
    Returns:
        bool: True if the participant is selected, False otherwise
    """
    # Generate a deterministic random number from the seed + ID
    seed_plus_id = seed + p_id
    hash_value = hashlib.sha256(seed_plus_id).digest()
    # Convert the hash to an integer
    my_val = int.from_bytes(hash_value, 'big')

    # Find the peer with the lowest hash value (winner)
    winner_peer_id = p_id
    lowest_val = my_val
    
    for peer_id in peers:
        # Convert string peer ID to bytes if needed
        peer_bytes = peer_id if isinstance(peer_id, bytes) else peer_id.encode()
        curr_val = int.from_bytes(hashlib.sha256(seed + peer_bytes).digest(), 'big')
        
        if curr_val < lowest_val:
            lowest_val = curr_val
            winner_peer_id = peer_bytes
    
    # Check if current peer is the winner
    is_winner = winner_peer_id == p_id
    
    if is_winner:
        print(f"Peer {p_id.hex()[:8]} won the lottery!")
    else:
        winner_id_hex = winner_peer_id.hex() if isinstance(winner_peer_id, bytes) else winner_peer_id
        print(f"Peer {p_id.hex()[:8]} lost the lottery, winner is {winner_id_hex[:8]}")
    
    return is_winner