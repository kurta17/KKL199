#!/usr/bin/env python3
"""Chess blockchain application using IPv8.

This application implements a proof-of-stake blockchain for recording chess matches.
"""

import os
import argparse
from asyncio import run, create_task, sleep
from typing import List
from ipv8_service import IPv8

# Use direct imports when running from ChessChain directory
from config.config import create_ipv8_config
from community.community import ChessCommunity
from utils.interface import manual_send_loop


async def start_communities(port: int = 8000, known_peers_args: List[str] | None = None) -> None:
    """Start the chess community.
    
    Args:
        port: Port to use for network communications
        known_peers_args: List of known peers as strings (e.g., "host:port")
    """
    # Parse known_peers_args into the required format: List[Tuple[str, int]]
    parsed_known_peers = []
    if known_peers_args:
        for peer_str in known_peers_args:
            try:
                host, peer_port_str = peer_str.split(':')
                parsed_known_peers.append((host, int(peer_port_str)))
            except ValueError:
                print(f"Warning: Could not parse peer '{peer_str}'. Expected format 'host:port'.")

    # Create and initialize IPv8 with the chess community
    ipv8 = IPv8(
        create_ipv8_config(port, known_peers=parsed_known_peers if parsed_known_peers else None),
        extra_communities={'ChessCommunity': ChessCommunity}
    )
    
    # Start IPv8 service
    await ipv8.start()
    
    # Get reference to our chess community
    comm = ipv8.get_overlay(ChessCommunity)
    print(f"ChessChain initialized: {comm.my_peer}")
    
    # Start the user interface
    create_task(manual_send_loop(comm))
    
    # Run indefinitely with a simple sleep loop
    try:
        while True:
            await sleep(10)
    except KeyboardInterrupt:
        print("\nShutting down ChessChain...")
        await ipv8.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChessChain: A blockchain for chess matches")
    parser.add_argument("-p", "--port", type=int, default=8000, 
                        help="Port to bind IPv8 to (default: 8000)")
    parser.add_argument("--peers", nargs='*', 
                        help="Optional list of known peers to connect to (e.g., localhost:8001 localhost:8002)")
    args = parser.parse_args()
    
    # Ensure chess_db directory exists
    os.makedirs("chess_db", exist_ok=True)
    
    # Start the application
    run(start_communities(args.port, args.peers))