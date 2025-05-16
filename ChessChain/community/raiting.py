class RatingManager:
    def __init__(self, db_env):
        self.rating_db = db_env.open_db(b'ratings', create=True)

    def get_user_rating(self, pubkey_hex: str) -> int:
        pubkey_bytes = bytes.fromhex(pubkey_hex)
        with self.db_env.begin(db=self.rating_db) as txn:
            value = txn.get(pubkey_bytes)
            if value is not None:
                return int(value.decode())
            return 1200  # Default rating

    def set_user_rating(self, pubkey_hex: str, rating: int) -> None:
        pubkey_bytes = bytes.fromhex(pubkey_hex)
        with self.db_env.begin(db=self.rating_db, write=True) as txn:
            txn.put(pubkey_bytes, str(rating).encode())

    def update_user_rating(self, pubkey_hex: str, delta: int) -> int:
        current = self.get_user_rating(pubkey_hex)
        new_rating = max(0, current + delta)
        self.set_user_rating(pubkey_hex, new_rating)
        return new_rating