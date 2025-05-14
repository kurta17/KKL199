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
            # Handle empty list case: e.g., by setting root to a predefined hash or raising error
            # For simplicity, let's assume items will not be empty or create a default empty root
            self.root = MerkleTree.Node(sha256(b''), None, None) 
            return
        self.items = items # Store original items if needed for proofs, otherwise just hashes
        
        # If items are not hashes themselves, hash them first.
        # Assuming 'items' are already hashes of the actual data.
        # If 'items' are the actual data (e.g., serialized transactions), 
        # they should be hashed before being passed to build_tree or here.
        # For this example, we'll assume items are already hashes.
        
        self.root = self.build_tree(self.items, 0, len(self.items) - 1)

    def build_tree(self, current_level_hashes: list[bytes], l: int, r: int) -> Node:  # noqa: E741
        if l == r:
            # Leaf node: hash is the item itself (assuming items are already hashes)
            return MerkleTree.Node(current_level_hashes[l], None, None)

        m = (l + r) >> 1
        left_child = self.build_tree(current_level_hashes, l, m)
        right_child = self.build_tree(current_level_hashes, m + 1, r)
        
        # Non-leaf node: hash is the hash of concatenated children's hashes
        return MerkleTree.Node(sha256(left_child.hash + right_child.hash), left_child, right_child)

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
