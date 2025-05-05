import asyncio
import argparse
from multiprocessing import Process
import os
import sys
from time import sleep
from ipv8_service import IPv8
from main import start_communities

NUM_PEERS = 100  # Default number, can be changed with command-line argument
BASE_PORT = 9000
DEFAULT_RUNTIME = 300  # 5 minutes

def worker(index, topology_type, num_peers):
    """Worker process to run an IPv8 peer with specified topology"""
    os.environ['IPV8_PORT'] = str(BASE_PORT + index)
    os.environ['COMMUNITY_TYPE'] = topology_type
    os.environ['NUM_PEERS'] = str(num_peers)
    asyncio.run(start_communities())

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Run multiple IPv8 peers with specified topology')
    parser.add_argument('--topology', choices=['sparse', 'dense'], default='dense', 
                        help='Network topology: sparse (5 peers max) or dense (all connected)')
    parser.add_argument('--peers', type=int, default=NUM_PEERS,
                        help=f'Number of peers to run (default: {NUM_PEERS})')
    parser.add_argument('--runtime', type=int, default=DEFAULT_RUNTIME,
                        help=f'Runtime in seconds (default: {DEFAULT_RUNTIME})')
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_arguments()
    
    # Set topology type based on arguments
    topology_type = 'SparseCommunity' if args.topology == 'sparse' else 'DenseCommunity'
    
    print(f"Starting {args.peers} peers with {args.topology} topology for {args.runtime} seconds")
    
    # Clean up any previous output file
    if os.path.exists("output.txt"):
        os.remove("output.txt")
    
    # Start the worker processes
    procs = []
    for i in range(args.peers):
        p = Process(target=worker, args=(i, topology_type, args.peers))
        p.start()
        procs.append(p)
        print(f"Started peer {i} on port {BASE_PORT + i}")
        sleep(0.5)  # Increased delay between starting peers to reduce contention
    
    try:
        print(f"All {args.peers} peers started. Running for {args.runtime} seconds...")
        sleep(args.runtime)
    except KeyboardInterrupt:
        print("Interrupted by user. Shutting down...")
    finally:
        # Terminate all processes
        for p in procs:
            try:
                p.terminate()
            except:
                pass
        
        print("All peers terminated. Analyzing results...")