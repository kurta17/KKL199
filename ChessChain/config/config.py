from typing import Dict, Any, List, Tuple
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs

# Use direct imports for running directly from ChessChain directory
from utils.utils import check_port
# from community.community import ChessCommunity # Not actually used in this file

def create_ipv8_config(port: int = 8000, known_peers: List[Tuple[str, int]] | None = None) -> Dict[str, Any]:
    """Create IPv8 configuration for the chess community.
    
    Args:
        port: Port to use for IPv8 communication
        known_peers: An optional list of (host, port) tuples for known peers.
        
    Returns:
        Dict[str, Any]: IPv8 configuration dictionary
    
    Raises:
        RuntimeError: If the port is already in use
    """
    if not check_port(port):
        raise RuntimeError(f"Port {port} bind failed")
        
    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.set_port(port)
    builder.add_key("my peer", "medium", "chess_peer_key.pem")

    bootstrappers_to_use = default_bootstrap_defs
    if known_peers:
        bootstrappers_to_use = known_peers

    builder.add_overlay(
        "ChessCommunity", "my peer",
        [WalkerDefinition(Strategy.RandomWalk, 5, {"timeout": 5.0})],
        bootstrappers_to_use,
        {},
        [('started',)]
    )
    
    return builder.finalize()