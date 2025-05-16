"""ChessChain - A blockchain for chess matches using IPv8.

This package implements a proof-of-stake blockchain for recording chess match transactions.
"""

__version__ = "0.1.0"

# Make core components accessible from the top-level package
from ChessChain.models.models import ChessTransaction
from ChessChain.community.community import ChessCommunity