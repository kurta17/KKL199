import networkx as nx
import matplotlib.pyplot as plt
import re
import numpy as np
import os
import argparse
from collections import defaultdict

NUM_PEERS = 100  # Match with run_peers.py
BASE_PORT = 9000

def generate_topology_graph(output_file="topology.png"):
    """Generate and visualize the network topology from log files"""
    G = nx.Graph()
    # Add nodes (peers identified by their ports)
    for i in range(NUM_PEERS):
        G.add_node(BASE_PORT + i)
    
    # Add edges based on the last logged connections
    connections_count = defaultdict(int)
    for i in range(NUM_PEERS):
        port = BASE_PORT + i
        try:
            with open(f"topology_{port}.txt", "r") as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    timestamp, peers_str = last_line.split(": ", 1)
                    if peers_str:
                        # Extract ports from tuple format like ('192.168.1.37', 8106)
                        peers = peers_str.split(",")
                        for peer in peers:
                            match = re.search(r"\((?:'[^']*', )?(\d+)\)", peer)
                            if match:
                                peer_port = int(match.group(1))
                                G.add_edge(port, peer_port)
                                connections_count[port] += 1
        except FileNotFoundError:
            print(f"Topology file for port {port} not found.")
    
    # Calculate network statistics
    avg_connections = np.mean(list(connections_count.values())) if connections_count else 0
    max_connections = max(connections_count.values()) if connections_count else 0
    min_connections = min(connections_count.values()) if connections_count else 0
    
    print(f"\n===== NETWORK TOPOLOGY STATISTICS =====")
    print(f"Total nodes: {G.number_of_nodes()}")
    print(f"Total connections: {G.number_of_edges()}")
    print(f"Average connections per node: {avg_connections:.2f}")
    print(f"Max connections: {max_connections}")
    print(f"Min connections: {min_connections}")
    
    # Calculate network density
    density = nx.density(G)
    print(f"Network density: {density:.4f}")
    
    # Check if the network is connected
    is_connected = nx.is_connected(G)
    print(f"Network fully connected: {'Yes' if is_connected else 'No'}")
    
    if not is_connected:
        components = list(nx.connected_components(G))
        print(f"Number of disconnected components: {len(components)}")
        
    # Calculate average shortest path length (only if connected)
    if is_connected and G.number_of_nodes() > 1:
        avg_path = nx.average_shortest_path_length(G)
        print(f"Average shortest path length: {avg_path:.2f}")
        
    # Draw and save the graph with node size proportional to connections
    plt.figure(figsize=(12, 12))
    pos = nx.spring_layout(G, seed=42)  # Consistent layout
    
    # Node sizes based on number of connections
    node_sizes = [50 + 20 * G.degree(n) for n in G.nodes()]
    
    # Draw nodes with size based on degree
    nx.draw(G, pos, with_labels=True, node_size=node_sizes, 
            node_color='skyblue', font_size=8, font_weight='bold')
    
    plt.title(f"Network Topology - {G.number_of_nodes()} nodes, {G.number_of_edges()} connections")
    plt.savefig(output_file)
    plt.close()
    print(f"Topology graph saved as '{output_file}'")

def analyze_gossip_stats(filename="output.txt"):
    """Analyze gossip protocol performance metrics from output file"""
    sent_total = 0
    dup_total = 0
    peer_count = 0
    peer_stats = {}
    
    try:
        with open(filename, "r") as f:
            for line in f:
                if "sent_messages" in line:
                    # Extract peer port and stats
                    match = re.search(r"Peer (\d+): sent_messages=(\d+), duplicate_received=(\d+)", line)
                    if match:
                        port = int(match.group(1))
                        sent = int(match.group(2))
                        dup = int(match.group(3))
                        peer_stats[port] = {'sent': sent, 'dup': dup}
                        sent_total += sent
                        dup_total += dup
                        peer_count += 1
        
        if peer_count == 0:
            print(f"No peer statistics found in '{filename}'")
            return
            
        # Calculate aggregate metrics
        avg_sent = sent_total / peer_count
        avg_dup = dup_total / peer_count
        
        # Calculate min/max/variance for sent messages
        sent_values = [stats['sent'] for stats in peer_stats.values()]
        dup_values = [stats['dup'] for stats in peer_stats.values()]
        
        min_sent = min(sent_values)
        max_sent = max(sent_values)
        var_sent = np.var(sent_values)
        
        min_dup = min(dup_values)
        max_dup = max(dup_values)
        
        # Calculate efficiency (lower duplicates is better)
        if sent_total > 0:
            efficiency = 1 - (dup_total / sent_total) if sent_total > 0 else 0
        else:
            efficiency = 0
        
        print(f"\n===== GOSSIP PROTOCOL STATISTICS =====")
        print(f"Total peers analyzed: {peer_count}")
        print(f"Total messages sent: {sent_total}")
        print(f"Total duplicate messages received: {dup_total}")
        print(f"Average messages sent per peer: {avg_sent:.2f}")
        print(f"Average duplicates received per peer: {avg_dup:.2f}")
        print(f"Message send variance: {var_sent:.2f}")
        print(f"Min/Max messages sent: {min_sent}/{max_sent}")
        print(f"Min/Max duplicates received: {min_dup}/{max_dup}")
        print(f"Protocol efficiency: {efficiency:.4f}")
        
        # Generate histogram of messages sent
        plt.figure(figsize=(10, 6))
        plt.hist(sent_values, bins=10, alpha=0.7, color='blue')
        plt.title('Distribution of Messages Sent per Peer')
        plt.xlabel('Number of Messages')
        plt.ylabel('Number of Peers')
        plt.grid(True, alpha=0.3)
        plt.savefig("messages_histogram.png")
        plt.close()
        print("Message distribution histogram saved as 'messages_histogram.png'")
        
    except FileNotFoundError:
        print(f"Output file '{filename}' not found. Please run the simulation with output redirection.")

def analyze_time_series():
    """Analyze temporal behavior of the network using stats files"""
    # Find all stats files
    stats_files = [f for f in os.listdir('.') if f.startswith('stats_') and f.endswith('.txt')]
    
    if not stats_files:
        print("No time series statistics files found.")
        return
        
    print(f"\n===== TEMPORAL ANALYSIS =====")
    print(f"Found {len(stats_files)} time series files")
    
    # Collect time series data
    time_data = defaultdict(list)
    messages_data = defaultdict(list)
    duplicates_data = defaultdict(list)
    
    for filename in stats_files:
        port = int(filename.split('_')[1].split('.')[0])
        
        try:
            with open(filename, 'r') as f:
                for line in f:
                    parts = line.strip().split(': ')
                    if len(parts) == 2:
                        timestamp = float(parts[0])
                        metrics = parts[1]
                        
                        # Extract message counts
                        sent_match = re.search(r"sent_messages=(\d+)", metrics)
                        dup_match = re.search(r"duplicate_received=(\d+)", metrics)
                        
                        if sent_match and dup_match:
                            sent = int(sent_match.group(1))
                            dup = int(dup_match.group(1))
                            
                            time_data[port].append(timestamp)
                            messages_data[port].append(sent)
                            duplicates_data[port].append(dup)
        except Exception as e:
            print(f"Error processing {filename}: {e}")
    
    # Plot message growth over time for a subset of peers
    plt.figure(figsize=(12, 8))
    
    # Select a representative subset of peers to avoid cluttering
    sample_peers = list(time_data.keys())[:5]  # Plot first 5 peers
    
    for port in sample_peers:
        # Normalize time to start from 0
        times = np.array(time_data[port])
        if len(times) > 0:
            normalized_times = times - times[0]
            plt.plot(normalized_times, messages_data[port], label=f'Peer {port}')
    
    plt.title('Message Count Growth Over Time')
    plt.xlabel('Time (seconds)')
    plt.ylabel('Cumulative Messages Sent')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig("message_growth.png")
    plt.close()
    print("Message growth plot saved as 'message_growth.png'")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Analyze P2P network results')
    parser.add_argument('--output', default='output.txt',
                      help='Path to the output statistics file')
    parser.add_argument('--topology', default='topology.png',
                      help='Output file for topology visualization')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    # Generate different visualizations
    generate_topology_graph(args.topology)
    analyze_gossip_stats(args.output)
    analyze_time_series()
    
    print("\nAnalysis complete. Check the generated visualization files for detailed results.")