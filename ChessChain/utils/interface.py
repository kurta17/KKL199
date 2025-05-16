import base64
from asyncio import create_task, sleep
 
from community.community0 import ChessCommunity
 
 
async def manual_send_loop(comm: ChessCommunity) -> None:
    """Interactive command loop for user to interact with the chess community."""
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
                print("Generating and sending fake match moves...")
                comm.generate_fake_match()
               
            elif cmd[0] == "showmempool":
                print(f"Mempool size: {len(comm.mempool)}")
                # Iterate over the values (ChessTransaction objects) of the mempool dictionary
                for idx, tx_object in enumerate(comm.mempool.values()):
                    # Access attributes from the ChessTransaction object
                    print(f"{idx+1}. Nonce: {tx_object.nonce}, Winner: {tx_object.winner}, Match ID: {tx_object.match_id}")
                   
            elif cmd[0] == "clearmempool":
                count = len(comm.mempool)
                comm.mempool.clear()
                print(f"Cleared {count} transactions from mempool")
               
            elif cmd[0] == "showstakes":
                print("=== Stakes ===")
                for k, v in comm.stakes.items():
                    print(f"{base64.b64encode(k)[:8].decode()}: {v} tokens")
                   
            elif cmd[0] == "showmoves" and len(cmd) == 2:
                match_id = cmd[1]
                print(f"\n=== Moves for match {match_id} ===")
                moves = comm.get_stored_moves(match_id)
                if not moves:
                    print("No moves found for this match.")
                for move in moves:
                    print(f"Move {move.id}: {move.player} played {move.move}")
                      
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
    print("  send                - Generate and send a fake match (moves + transaction)")
    print("  showmempool         - Show transactions in the mempool")
    print("  clearmempool        - Clear all transactions from the mempool")
    print("  showstakes          - Show stake distribution")
    print("  showmoves <match_id> - Show stored moves for a match")
    print("")