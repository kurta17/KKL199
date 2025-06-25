import base64
from asyncio import create_task, sleep
from typing import Optional
from community.community import ChessCommunity

async def manual_send_loop(comm: Optional[ChessCommunity]) -> None:
    """Interactive command loop for user to interact with the chess community."""
    if comm is None:
        print("Error: ChessCommunity instance not provided.")
        return

    print("Chess blockchain interface started. Type 'help' for available commands.")
    while True:
        try:
            cmd = input("ChessChain > ").strip().split(maxsplit=1)
            if not cmd:
                continue

            command = cmd[0].lower()
            args = cmd[1] if len(cmd) > 1 else ""

            if command == "help":
                print_help()

            elif command == "stake":
                try:
                    amount = int(args)
                    if amount <= 0:
                        print("Invalid amount. Please enter a positive number.")
                    else:
                        comm.data_manager.stake_tokens(amount)
                except ValueError:
                    print("Invalid amount. Please enter a number (e.g., 'stake 100').")

            elif command == "show":
                print("\n=== Transactions ===")
                try:
                    transactions = comm.data_manager.get_stored_transactions()
                    if not transactions:
                        print("No transactions found.")
                    for t in transactions:
                        print(f"Nonce: {t.nonce}, Match: {t.match_id}, Winner: {t.winner}, Proposer: {t.proposer_pubkey_hex[:8]}")
                except Exception as e:
                    print(f"Error retrieving transactions: {e}")
                
                print("\n=== Peers ===")
                peers = comm.get_peers()
                if not peers:
                    print("No peers connected.")
                for peer in peers:
                    print(f"Peer: {peer}")

            elif command == "send":
                print("Generating and sending fake match moves...")
                comm.generate_fake_match()

            elif command == "showmempool":
                print("\n=== Mempool Transactions ===")
                try:
                    mempool = comm.data_manager.get_mempool()
                    if not mempool:
                        print("Mempool is empty.")
                    for idx, tx in enumerate(mempool.values(), 1):
                        print(f"{idx}. Nonce: {tx.nonce}, Match: {tx.match_id}, Winner: {tx.winner}, Proposer: {tx.proposer_pubkey_hex[:8]}")
                    print(f"Mempool size: {len(mempool)}")
                except Exception as e:
                    print(f"Error retrieving mempool: {e}")

            elif command == "clearmempool":
                try:
                    count = len(comm.data_manager.get_mempool())
                    comm.data_manager.mempool.clear()
                    print(f"Cleared {count} transactions from mempool")
                except Exception as e:
                    print(f"Error clearing mempool: {e}")

            elif command == "showstakes":
                print("\n=== Stakes ===")
                try:
                    stakes = comm.data_manager.stakes
                    if not stakes:
                        print("No stakes recorded.")
                    for k, v in stakes.items():
                        key_str = base64.b64encode(k).decode()[:8]
                        print(f"{key_str}: {v} tokens")
                except Exception as e:
                    print(f"Error retrieving stakes: {e}")

            elif command == "showmoves":
                if not args:
                    print("Error: Please provide a match ID (e.g., 'showmoves 8228e1fd-8a6c-491e-8204-c4b26933a690').")
                else:
                    match_id = args.strip()
                    print(f"\n=== Moves for match {match_id} ===")
                    try:
                        moves = comm.data_manager.get_stored_moves(match_id)
                        if not moves:
                            print("No moves found for this match.")
                        for move in moves:
                            print(f"Move {move.id}: {move.player[:8]} played {move.move} at {move.timestamp}")
                    except Exception as e:
                        print(f"Error retrieving moves: {e}")

            else:
                print(f"Unknown command: {command}")
                print_help()

        except Exception as e:
            print(f"Error processing command: {e}")

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