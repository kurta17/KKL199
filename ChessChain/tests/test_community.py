import unittest
from unittest.mock import patch, MagicMock
import hashlib
import time

# It's common to need to adjust the Python path for tests to find modules
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from community.community import ChessCommunity, CommunitySettings
from community.messages import ProposedBlockPayload # Assuming this is the correct import
from models.models import ChessTransaction, MoveData # Assuming these are needed
from ipv8.test.base import TestBase
from ipv8.keyvault.private.libnaclkey import LibNaCLSK
from ipv8.peer import Peer
from ipv8.lazy_community import lazy_wrapper

# Helper function to create a mock peer
def create_mock_peer(secret_key_for_generating_public_key=None):
    # sk is the secret key, used to derive the public key and mid for mocking
    sk = secret_key_for_generating_public_key if secret_key_for_generating_public_key else LibNaCLSK()
    
    # 1. Create a mock for the PublicKey object that Peer.key will hold.
    #    A real Peer object's .key attribute is its public key.
    mock_public_key_obj = MagicMock(spec=sk.pub()) # Use a real public key (sk.pub()) as spec
    mock_public_key_obj.key_to_bin.return_value = sk.pub().key_to_bin()
    # If other methods of the public key are called (e.g., verify), they'd be mocked on mock_public_key_obj.

    # 2. Create the mock for the Peer object itself.
    peer_mock = MagicMock(spec=Peer)
    peer_mock.key = mock_public_key_obj
    
    # Calculate mid correctly from the public key's binary representation
    public_key_binary_for_mid = sk.pub().key_to_bin()
    peer_mock.mid = hashlib.sha1(public_key_binary_for_mid).digest()[:20] # IPv8 uses SHA1 for mid (20 bytes)
    
    peer_mock.address = ('127.0.0.1', 0) # Default mock address

    return peer_mock

class TestChessCommunityPoS(TestBase):
    def setUp(self):
        super().setUp()
        self.my_key = LibNaCLSK()
        self.mock_ipv8 = MagicMock()
        self.mock_ipv8.keys = {'my_peer_id': self.my_key} # Simplified
        self.mock_ipv8.my_peer = create_mock_peer(self.my_key) # Use the updated helper
        self.mock_ipv8.endpoint = MagicMock()
        self.mock_ipv8.endpoint.get_address.return_value = ('127.0.0.1', 8090)
        
        self.settings = CommunitySettings()
        self.settings.max_peers = 20
        self.settings.target_fanout = 5

        self.community = ChessCommunity(self.settings, self.mock_ipv8, self.my_key)
        self.community.my_peer = self.mock_ipv8.my_peer # Ensure my_peer is set
        self.community.network = MagicMock() # Mock the network overlay
        self.community.endpoint = self.mock_ipv8.endpoint # Ensure endpoint is set

        # Mock databases
        self.community.transaction_db = MagicMock()
        self.community.moves_db = MagicMock()
        self.community.block_db = MagicMock()
        self.community.stakes_db = MagicMock()

        # Initialize some state
        self.community.stakes = {self.my_key.pub().key_to_bin().hex(): 100} # Example stake
        self.community.current_round_seed = hashlib.sha256(b"initial_seed").hexdigest()
        self.community.mempool = {} # Clear mempool

        # Additional keys for testing proposer selection
        self.key1 = LibNaCLSK()
        self.key2 = LibNaCLSK()
        self.key3 = LibNaCLSK()

        self.pubkey_hex_my = self.my_key.pub().key_to_bin().hex()
        self.pubkey_hex_1 = self.key1.pub().key_to_bin().hex()
        self.pubkey_hex_2 = self.key2.pub().key_to_bin().hex()
        self.pubkey_hex_3 = self.key3.pub().key_to_bin().hex()

    def tearDown(self):
        self.community.unload() # Ensure any scheduled tasks are cancelled
        super().tearDown()

    def test_initialization(self):
        """Test basic initialization of the community and PoS components."""
        self.assertIsNotNone(self.community)
        self.assertEqual(self.community.current_round_seed, hashlib.sha256(b"initial_seed").hexdigest())
        self.assertIn(self.pubkey_hex_my, self.community.stakes)

    def _calculate_expected_proposer(self, seed_hex, stakes):
        if not stakes:
            return None
        scores = {}
        for pubkey_hex, stake_amount in stakes.items():
            h = hashlib.sha256()
            h.update(seed_hex.encode('utf-8'))
            h.update(pubkey_hex.encode('utf-8'))
            score = int.from_bytes(h.digest(), 'big') * stake_amount
            scores[pubkey_hex] = score
        
        if not scores: # Should not happen if stakes is not empty
            return None
        
        return max(scores, key=scores.get)

    def test_checking_proposer_selects_correctly(self):
        """Test that checking_proposer selects the correct proposer based on stakes and seed."""
        stakes = {
            self.pubkey_hex_my: 100,
            self.pubkey_hex_1: 50,
            self.pubkey_hex_2: 200,
        }
        self.community.stakes = stakes
        seed = "a_deterministic_seed_for_testing"
        
        expected_proposer = self._calculate_expected_proposer(seed, stakes)
        selected_proposer = self.community.checking_proposer(seed)
        
        self.assertEqual(selected_proposer, expected_proposer)

    def test_checking_proposer_single_staker(self):
        """Test that if only one peer has a stake, it is always selected."""
        stakes = {
            self.pubkey_hex_1: 100
        }
        self.community.stakes = stakes
        seed = "another_seed"
        
        expected_proposer = self.pubkey_hex_1
        selected_proposer = self.community.checking_proposer(seed)
        self.assertEqual(selected_proposer, expected_proposer)

    def test_checking_proposer_no_stakers(self):
        """Test that if no peers have stakes, no proposer is selected."""
        self.community.stakes = {}
        seed = "yet_another_seed"
        
        selected_proposer = self.community.checking_proposer(seed)
        self.assertIsNone(selected_proposer)

    def test_checking_proposer_equal_stakes_deterministic_outcome(self):
        """Test that with equal stakes, the outcome is deterministic for a given seed."""
        stakes = {
            self.pubkey_hex_1: 100,
            self.pubkey_hex_2: 100,
            self.pubkey_hex_3: 100,
        }
        self.community.stakes = stakes
        seed = "equal_stakes_seed"

        expected_proposer = self._calculate_expected_proposer(seed, stakes)
        selected_proposer = self.community.checking_proposer(seed)
        self.assertEqual(selected_proposer, expected_proposer, "Proposer should be deterministic for the same seed and stakes.")

        # Sanity check: ensure a different seed *could* produce a different winner (though not guaranteed with hash collisions)
        # This is more of a check on the test's _calculate_expected_proposer logic with the community's
        different_seed = "equal_stakes_seed_variant"
        possibly_different_expected_proposer = self._calculate_expected_proposer(different_seed, stakes)
        possibly_different_selected_proposer = self.community.checking_proposer(different_seed)
        self.assertEqual(possibly_different_selected_proposer, possibly_different_expected_proposer)

if __name__ == '__main__':
    unittest.main()
