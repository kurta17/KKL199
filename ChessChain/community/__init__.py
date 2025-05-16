"""ChessChain community module.

This module contains the IPv8 community implementation for chess transactions.
"""

# This file helps resolve circular imports by defining the proper import order
# The imports below are intentionally NOT at the top of the file

# First we define empty class for forward reference
class ChessCommunity:
    pass

# Import all component modules, but AVOID importing from community0.py
# to prevent circular imports
from .blockchain import Blockchain
from .consensus import Consensus
from .sync import Sync
from .transaction import Transaction
from .moves import Moves
from .proposer import Proposer
from .stake import Stake
from .network import ChessNetwork  # Updated to use renamed class

# Now import the real ChessCommunity class, replacing our placeholder
from .community0 import ChessCommunity

# Define what should be accessible when importing from this module
__all__ = ['ChessCommunity']