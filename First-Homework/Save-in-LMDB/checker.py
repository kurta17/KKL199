import lmdb

def inspect_lmdb(db_path='transactions_db'):
    # Open the LMDB environment in read-only mode
    env = lmdb.open(db_path, readonly=True, max_dbs=1)
    
    # Open the 'transactions' sub-database
    db = env.open_db(b'transactions')
    
    # Read and print all key-value pairs
    with env.begin(db=db) as txn:
        cursor = txn.cursor()
        print("Transactions in LMDB:")
        for key, value in cursor:
            # Decode bytes to strings for readability
            nonce = key.decode()
            pubkey = value.decode()
            print(f"Nonce: {nonce}, Pubkey: {pubkey}")
        
        # Optional: Count total entries
        print(f"Total transactions: {txn.stat()['entries']}")

if __name__ == "__main__":
    inspect_lmdb()