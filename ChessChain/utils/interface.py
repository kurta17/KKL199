import base64
from asyncio import create_task, sleep

# Update import for direct running from ChessChain directory
from community.community import ChessCommunity


async def manual_send_loop(comm: ChessCommunity) -> None:
    """Interactive command loop for user to interact with the chess community.
    
    Args:
        comm: The chess community instance
    """
    print("Chess blockchain interface started. Type 'help' for available commands.")
    while True:
        try:
            cmd = input("ChessChain > ").split()
            if not cmd: 
                continue
                
            if cmd[0] == "help":
                print_help()
                
            elif cmd[0] == "stake" and len(cmd) == 2:
                try:
                    amount = int(cmd[1])
                    comm.stake_tokens(amount)
                except ValueError:
                    print("Invalid amount. Please enter a number.")
                    
            elif cmd[0] == "show":
                print("\n=== Transactions ===")
                for t in comm.get_stored_transactions():
                    print(f"{t.nonce}: winner={t.winner}")
                print("\n=== Peers ===")
                for peer in comm.get_peers():
                    print(f"Peer: {peer}")
                    
            elif cmd[0] == "send":
                tx = comm.generate_fake_match()
                comm.send_transaction(tx)
                
            elif cmd[0] == "showmempool":
                print(f"Mempool size: {len(comm.mempool)}")
                for idx, tx in enumerate(comm.mempool):
                    print(f"{idx+1}. {tx.nonce}: winner={tx.winner}")
                    
            elif cmd[0] == "clearmempool":
                count = len(comm.mempool)
                comm.mempool.clear()
                print(f"Cleared {count} transactions from mempool")
                
            elif cmd[0] == "showstakes":
                print("=== Stakes ===")
                for k, v in comm.stakes.items():
                    print(f"{base64.b64encode(k)[:8].decode()}: {v} tokens")
                    
            else:
                print(f"Unknown command: {cmd[0]}")
                print_help()
                
        except Exception as e:
            print(f"Error: {e}")
            
        await sleep(0.1)  # Small sleep to not block the event loop


def print_help():
    """Print available commands."""
    print("\nAvailable commands:")
    print("  help                - Show this help message")
    print("  stake <amount>      - Stake tokens in the system")
    print("  show                - Show stored transactions and peers")
    print("  send                - Generate and send a fake match transaction")
    print("  showmempool         - Show transactions in the mempool")
    print("  clearmempool        - Clear all transactions from the mempool")
    print("  showstakes          - Show stake distribution")
    print("")