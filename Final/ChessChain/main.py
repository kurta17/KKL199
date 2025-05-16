#!/usr/bin/env python3
"""Chess blockchain application using IPv8.

This application implements a proof-of-stake blockchain for recording chess matches.
"""
import ctypes
import os
import sys
import importlib.util
import argparse
from asyncio import run, create_task, sleep

# Use direct imports when running from ChessChain directory
from ipv8_service import IPv8
from config.config import create_ipv8_config
from community.community import ChessCommunity
from utils.interface import manual_send_loop

# Check for uvicorn availability
UVICORN_AVAILABLE = importlib.util.find_spec("uvicorn") is not None
if not UVICORN_AVAILABLE:
    print("uvicorn not available, API functionality will be limited")
    print("You can install uvicorn with: pip install uvicorn fastapi")


async def start_api_server(api_port: int, ipv8_instance=None, chess_community=None):
    """Start the API server for external applications to interact with the blockchain.
    
    Args:
        api_port: Port for the API server
        ipv8_instance: Reference to the running IPv8 instance
        chess_community: Reference to the chess community
    """
    if not UVICORN_AVAILABLE:
        print("Cannot start API server: uvicorn not installed")
        print("Install with: pip install uvicorn fastapi")
        return
        
    try:
        # Make the instances available to the API
        if ipv8_instance and chess_community:
            # Dynamically import and configure API
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            import api
            api.ipv8_instance = ipv8_instance
            api.chess_community = chess_community
            print("API configured with existing blockchain instance")
        
        # Import uvicorn here to avoid import errors if not available
        import uvicorn
        
        # Configure the server
        config = uvicorn.Config(
            "api:app", 
            host="0.0.0.0", 
            port=api_port,
            log_level="info",
            reload=False
        )
        
        # Start the server
        server = uvicorn.Server(config)
        print(f"Blockchain API running on port {api_port}")
        await server.serve()
    except Exception as e:
        print(f"Error starting API server: {e}")


async def start_communities(port: int = 8000, api_port: int = None) -> None:
    """Start the chess community.
    
    Args:
        port: Port to use for network communications
        api_port: Optional port for REST API server
    """
    # Create and initialize IPv8 with the chess community
    ipv8 = IPv8(
        create_ipv8_config(port), 
        extra_communities={'ChessCommunity': ChessCommunity}
    )
    
    # Start IPv8 service
    await ipv8.start()
    
    # Get reference to our chess community
    comm = ipv8.get_overlay(ChessCommunity)
    print(f"ChessChain initialized: {comm.my_peer}")
    
    # Tasks to run
    tasks = []
    
    # Start API server if requested
    if api_port:
        print(f"Starting API server on port {api_port}...")
        tasks.append(start_api_server(api_port, ipv8, comm))
    
    # Start the user interface
    tasks.append(manual_send_loop(comm))
    
    # Run indefinitely with a simple sleep loop or until interrupted
    try:
        # Start additional tasks
        for task in tasks:
            create_task(task)
            
        # Main loop
        while True:
            await sleep(10)
    except KeyboardInterrupt:
        print("\nShutting down ChessChain...")
        await ipv8.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChessChain: A blockchain for chess matches")
    parser.add_argument("-p", "--port", type=int, default=8000, 
                        help="Port to bind IPv8 to (default: 8000)")
    parser.add_argument("--api", action="store_true", help="Start with API server")
    parser.add_argument("--api-port", type=int, default=8080,
                      help="Port for API server if enabled (default: 8080)")
    args = parser.parse_args()
    
    # Ensure chess_db directory exists
    os.makedirs("chess_db", exist_ok=True)
    
    # Start the application
    api_port = args.api_port if args.api else None
    run(start_communities(args.port, api_port))