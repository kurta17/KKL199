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


# In utils/utils.py:
def lottery_selection(seed_plus_id: bytes, my_stake: int, total_stake: int) -> bool:
    """Lottery-based random selection based on stake.
    
    Args:
        seed_plus_id: Combined seed and validator ID
        my_stake: Stake of the participant
        total_stake: Total stake in the system
        
    Returns:
        bool: True if the participant is selected, False otherwise
    """
    # Generate a deterministic random number from the seed + ID
    hash_value = hashlib.sha256(seed_plus_id).digest()
    random_value = int.from_bytes(hash_value, 'big') / 2**256  # Normalize to [0,1)
    
    # Calculate probability of selection based on stake
    selection_probability = my_stake / total_stake if total_stake > 0 else 0
    
    # Select if the random value is less than the selection probability
    return random_value < selection_probability
