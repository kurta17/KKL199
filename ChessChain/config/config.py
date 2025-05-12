from typing import Dict, Any
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs

# Use direct imports for running directly from ChessChain directory
from utils.utils import check_port
from community.community import ChessCommunity


def create_ipv8_config(port: int = 8000) -> Dict[str, Any]:
    """Create IPv8 configuration for the chess community.
    
    Args:
        port: Port to use for IPv8 communication
        
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
    builder.add_overlay(
        "ChessCommunity", "my peer",
        [WalkerDefinition(Strategy.RandomWalk, 5, {"timeout": 5.0})],
        default_bootstrap_defs,
        {},
        [('started',)]
    )
    
    return builder.finalize()