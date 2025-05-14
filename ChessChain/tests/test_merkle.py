import unittest
import hashlib
from utils.merkle import MerkleTree

class TestMerkleTree(unittest.TestCase):

    def test_empty_tree(self):
        """Test Merkle tree with no data."""
        mt = MerkleTree([])
        self.assertIsNone(mt.get_root(), "Root of an empty tree should be None.")

    def test_single_item(self):
        """Test Merkle tree with a single item."""
        data = [b"item1"]
        mt = MerkleTree(data)
        expected_root = hashlib.sha256(data[0]).digest()
        self.assertEqual(mt.get_root(), expected_root, "Root for a single item is its hash.")

    def test_two_items(self):
        """Test Merkle tree with two items."""
        data = [b"item1", b"item2"]
        mt = MerkleTree(data)
        hash1 = hashlib.sha256(data[0]).digest()
        hash2 = hashlib.sha256(data[1]).digest()
        expected_root = hashlib.sha256(hash1 + hash2).digest()
        self.assertEqual(mt.get_root(), expected_root, "Merkle root for two items is incorrect.")

    def test_three_items(self):
        """Test Merkle tree with three items (odd number)."""
        data = [b"item1", b"item2", b"item3"]
        mt = MerkleTree(data)
        hash1 = hashlib.sha256(data[0]).digest()
        hash2 = hashlib.sha256(data[1]).digest()
        hash3 = hashlib.sha256(data[2]).digest()
        
        # Level 1
        node12 = hashlib.sha256(hash1 + hash2).digest()
        node33 = hashlib.sha256(hash3 + hash3).digest() # Duplicate last item's hash
        
        # Level 2 (Root)
        expected_root = hashlib.sha256(node12 + node33).digest()
        self.assertEqual(mt.get_root(), expected_root, "Merkle root for three items is incorrect.")

    def test_four_items(self):
        """Test Merkle tree with four items (even number)."""
        data = [b"item1", b"item2", b"item3", b"item4"]
        mt = MerkleTree(data)
        hash1 = hashlib.sha256(data[0]).digest()
        hash2 = hashlib.sha256(data[1]).digest()
        hash3 = hashlib.sha256(data[2]).digest()
        hash4 = hashlib.sha256(data[3]).digest()

        # Level 1
        node12 = hashlib.sha256(hash1 + hash2).digest()
        node34 = hashlib.sha256(hash3 + hash4).digest()

        # Level 2 (Root)
        expected_root = hashlib.sha256(node12 + node34).digest()
        self.assertEqual(mt.get_root(), expected_root, "Merkle root for four items is incorrect.")

    def test_multiple_items_complex(self):
        """Test with a more complex scenario of 5 items."""
        data = [b"A", b"B", b"C", b"D", b"E"]
        mt = MerkleTree(data)

        hA = hashlib.sha256(b"A").digest()
        hB = hashlib.sha256(b"B").digest()
        hC = hashlib.sha256(b"C").digest()
        hD = hashlib.sha256(b"D").digest()
        hE = hashlib.sha256(b"E").digest()

        # Level 1
        hAB = hashlib.sha256(hA + hB).digest()
        hCD = hashlib.sha256(hC + hD).digest()
        hEE = hashlib.sha256(hE + hE).digest() # E is duplicated

        # Level 2
        hABCD = hashlib.sha256(hAB + hCD).digest()
        hEEEE = hashlib.sha256(hEE + hEE).digest() # hEE is duplicated as it's alone on this level

        # Level 3 (Root)
        expected_root = hashlib.sha256(hABCD + hEEEE).digest()
        self.assertEqual(mt.get_root(), expected_root, "Merkle root for five items is incorrect.")

    def test_data_modification_does_not_affect_tree(self):
        """Ensure modifying the input list after tree creation doesn't change the root."""
        data = [b"original1", b"original2"]
        mt = MerkleTree(data)
        original_root = mt.get_root()
        
        # Modify the original data list
        data.append(b"new_data")
        data[0] = b"modified_data"
        
        self.assertEqual(mt.get_root(), original_root, 
                         "Modifying original data list affected the Merkle tree's root.")

if __name__ == '__main__':
    unittest.main()
