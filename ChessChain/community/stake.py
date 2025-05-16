from typing import TYPE_CHECKING

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from . import ChessCommunity
else:
    from . import ChessCommunity

class Stake:
    def __init__(self, community: 'ChessCommunity'):
        self.community = community
        self.stakes = community.stakes
        self.db_env = community.db_env
        self.stake_db = community.stake_db
        self.pubkey_bytes = community.pubkey_bytes

    def stake_tokens(self, amount: int) -> None:
        pid = self.pubkey_bytes
        new = self.stakes.get(pid, 0) + amount
        with self.db_env.begin(db=self.stake_db, write=True) as tx:
            tx.put(pid, str(new).encode())
        self.stakes[pid] = new
        print(f"Staked {amount}, total stake: {new}")

    def total_stake(self) -> int:
        return sum(self.stakes.values())