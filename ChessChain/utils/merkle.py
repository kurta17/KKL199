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

    def __init__(self, items: list[str | bytes]) -> None:
        if not items:
            self.root: MerkleTree.Node | None = None
            return

        # First, make sure all items are bytes before hashing
        byte_items = []
        for item in items:
            if isinstance(item, str):
                byte_items.append(item.encode('utf-8'))
            else:
                byte_items.append(item)

        # Create leaf nodes by hashing each item
        leaves = [MerkleTree.Node(sha256(item), None, None) for item in byte_items]

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
            return self.root.hash.hex()
        return None