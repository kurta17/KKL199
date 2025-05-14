from typing import Self
import hashlib

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

class MerkleTree:
    class Node:
        def __init__(self, hash_: bytes, left: Self | None, right: Self | None) -> None:
            self.hash = hash_
            self.left = left
            self.right = right

        hash: bytes
        left: Self | None
        right: Self | None

    def __init__(self, items: list[bytes]) -> None:
        if not items:
            self.root: MerkleTree.Node | None = None
            return

        # First, create leaf nodes by hashing each item
        leaves = [MerkleTree.Node(sha256(item), None, None) for item in items]

        if not leaves: # Should not happen if items is not empty, but as a safeguard
            self.root = None
            return
        
        if len(leaves) == 1:
            self.root = leaves[0]
            return

        current_level_nodes = leaves
        while len(current_level_nodes) > 1:
            next_level_nodes = []
            for i in range(0, len(current_level_nodes), 2):
                left_child = current_level_nodes[i]
                if i + 1 < len(current_level_nodes):
                    right_child = current_level_nodes[i+1]
                else:
                    # Odd number of nodes, duplicate the last one
                    right_child = left_child 
                
                parent_hash = sha256(left_child.hash + right_child.hash)
                next_level_nodes.append(MerkleTree.Node(parent_hash, left_child, right_child))
            current_level_nodes = next_level_nodes
        
        self.root = current_level_nodes[0]

    def get_root(self) -> bytes | None:
        """Returns the hash of the root node of the Merkle tree."""
        if self.root:
            return self.root.hash
        return None

    # Example of how get_verify_data (Merkle Proof) might be structured
    # This is a more complex part and would need careful implementation
    # def get_verify_data(self, index: int) -> list[bytes]:
    #     if not self.items or index < 0 or index >= len(self.items):
    #         return [] # Or raise an error

    #     proof = []
    #     
    #     # This requires a way to navigate the tree or reconstruct paths
    #     # The current build_tree builds bottom-up. For proofs, you often
    #     # need to store the tree structure or re-derive paths.
    #     # A common way is to build levels:
    #     
    #     levels = [self.items] # Start with leaf hashes
    #     current_level = self.items
    #     
    #     while len(current_level) > 1:
    #         next_level = []
    #         for i in range(0, len(current_level), 2):
    #             left_hash = current_level[i]
    #             if i + 1 < len(current_level):
    #                 right_hash = current_level[i+1]
    #             else: # Odd number of hashes, duplicate the last one
    #                 right_hash = left_hash 
    #             parent_hash = sha256(left_hash + right_hash)
    #             next_level.append(parent_hash)
    #         levels.append(next_level)
    #         current_level = next_level
            
    #     # Now traverse 'levels' from bottom up to collect proof
    #     # For a given index, determine if it's a left or right child at each level
    #     # and add its sibling to the proof.
    #     
    #     current_idx_in_level = index
    #     for level_idx in range(len(levels) - 1): # Iterate up to the level before root
    #         level_nodes = levels[level_idx]
    #         is_right_node = current_idx_in_level % 2 != 0
    #         sibling_idx = current_idx_in_level - 1 if is_right_node else current_idx_in_level + 1
            
    #         if sibling_idx < len(level_nodes):
    #             proof.append(level_nodes[sibling_idx])
    #         else: # If it was an odd one out that got duplicated, its "sibling" was itself
    #             proof.append(level_nodes[current_idx_in_level]) 
                
    #         current_idx_in_level //= 2 # Move to parent's index in next level
            
    #     return proof

# Example usage (assuming items are already hashes):
# tx_hashes = [sha256(b"tx1"), sha256(b"tx2"), sha256(b"tx3"), sha256(b"tx4")]
# tree = MerkleTree(tx_hashes)
# print(f"Merkle Root: {tree.root.hash.hex()}")

# To verify a transaction (e.g., tx_hashes[0])
# proof = tree.get_verify_data(0) # This method needs to be fully implemented
# target_hash = tx_hashes[0]
# calculated_root = target_hash
# for sibling_hash in proof:
#    # The order of concatenation (left+right or right+left) depends on 
#    # whether the current hash is a left or right child. This needs to be
#    # determined during proof generation or passed along with the proof.
#    # Assuming for simplicity, we know the order or the proof contains tuples (hash, is_left_sibling)
#    # For this example, let's assume we always hash (current_hash + sibling_hash) if current is left,
#    # or (sibling_hash + current_hash) if current is right. This logic is complex.
#    pass # Placeholder for actual verification logic
