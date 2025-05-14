import sys
import os
import traceback
from ipv8.messaging.payload_dataclass import DataClassPayload
from ipv8.messaging.serialization import default_serializer, ListOf, VarLenUtf8  # Import ListOf and VarLenUtf8
from dataclasses import dataclass

# Adjust the path to import from the parent directory (ChessChain)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.models import ProposedBlockPayload, MoveData

# Register the custom packer for List[str] which DataClassPayload seems to expect
# Format 'arrayH-varlenHutf8': List of (UTF-8 strings prefixed by H-length), count of items prefixed by H
custom_list_str_packer = ListOf(VarLenUtf8('>H'), length_format='>H')
default_serializer.add_packer('arrayH-varlenHutf8', custom_list_str_packer)

def test_move_data_serialization():
    print("\nTesting MoveData serialization/deserialization...")
    move_instance = MoveData(
        id=1,
        player="player1_pubkey_hex",
        move="e2e4",
        signature="dummy_move_signature"
    )
    print(f"Original MoveData instance: {move_instance}")
    print(f"Type of MoveData instance: {type(move_instance)}")
    print(f"MRO of MoveData instance type: {type(move_instance).__mro__}")
    print(f"Has 'to_bytes' attr on MoveData class: {hasattr(MoveData, 'to_bytes')}")
    print(f"Has 'from_bytes' attr on MoveData class: {hasattr(MoveData, 'from_bytes')}")

    try:
        # Use default_serializer.pack_serializable
        serialized_move = default_serializer.pack_serializable(move_instance)
        print(f"Serialized MoveData (first 50 bytes): {serialized_move[:50]}...")
        
        # Use default_serializer.unpack_serializable
        deserialized_move, offset = default_serializer.unpack_serializable(MoveData, serialized_move)
        print(f"Deserialized MoveData instance: {deserialized_move}, offset: {offset}")
        assert move_instance.id == deserialized_move.id
        assert move_instance.player == deserialized_move.player
        assert move_instance.move == deserialized_move.move
        assert move_instance.signature == deserialized_move.signature
        print("MoveData serialization/deserialization test PASSED!")
        return True
    except Exception as e:
        print(f"MoveData test FAILED: {e}")
        print(traceback.format_exc())
        return False

def test_proposed_block_payload_serialization():
    print("\nTesting ProposedBlockPayload serialization/deserialization...")
    dummy_tx_hashes = ["tx_hash_1_placeholder", "tx_hash_2_placeholder", "tx_hash_3_placeholder"]
    dummy_merkle_root = "merkle_root_placeholder_abc123xyz789"
    
    payload_instance = ProposedBlockPayload(
        round_seed_hex="round_seed_placeholder_def456",
        transaction_hashes=dummy_tx_hashes,
        merkle_root=dummy_merkle_root,
        proposer_pubkey_hex="proposer_pubkey_placeholder_ghi789",
        signature="signature_placeholder_jkl012"
    )
    print(f"Original ProposedBlockPayload instance: {payload_instance}")
    print(f"Type of ProposedBlockPayload instance: {type(payload_instance)}")
    print(f"MRO of ProposedBlockPayload instance type: {type(payload_instance).__mro__}")
    print(f"Has 'to_bytes' attr on ProposedBlockPayload class: {hasattr(ProposedBlockPayload, 'to_bytes')}")
    print(f"Has 'from_bytes' attr on ProposedBlockPayload class: {hasattr(ProposedBlockPayload, 'from_bytes')}")

    try:
        # Serialization
        # Use default_serializer.pack_serializable
        serialized_payload = default_serializer.pack_serializable(payload_instance)
        print(f"Serialized ProposedBlockPayload (first 50 bytes): {serialized_payload[:50]}...")
        
        # Deserialization
        # Use default_serializer.unpack_serializable
        deserialized_payload, offset = default_serializer.unpack_serializable(ProposedBlockPayload, serialized_payload)
        print(f"Deserialized ProposedBlockPayload instance: {deserialized_payload}, offset: {offset}")

        # Verification
        assert payload_instance.round_seed_hex == deserialized_payload.round_seed_hex, "round_seed_hex mismatch"
        assert payload_instance.transaction_hashes == deserialized_payload.transaction_hashes, "transaction_hashes mismatch"
        assert payload_instance.merkle_root == deserialized_payload.merkle_root, "merkle_root mismatch"
        assert payload_instance.proposer_pubkey_hex == deserialized_payload.proposer_pubkey_hex, "proposer_pubkey_hex mismatch"
        assert payload_instance.signature == deserialized_payload.signature, "signature mismatch"
        
        print("ProposedBlockPayload serialization/deserialization test PASSED!")
        return True

    except Exception as e:
        print(f"ProposedBlockPayload test FAILED: {e}")
        print(traceback.format_exc())
        return False

def test_dataclass_payload_methods():
    """Test if DataClassPayload itself has to_bytes and from_bytes."""
    @dataclass
    class SimplePayload(DataClassPayload):
        msg_id = 1
        some_data: int

        # Keep __init__ if DataClassPayload doesn't handle it automatically
        pass

    instance = SimplePayload(some_data=123)
    print(f"MRO for SimplePayload: {SimplePayload.mro()}")
    print(f"Instance of SimplePayload: {instance}")
    
    # Attempt to call to_bytes to see if it executes
    try:
        # Use default_serializer.pack_serializable
        byte_data = default_serializer.pack_serializable(instance)
        print(f"SimplePayload.to_bytes() (via default_serializer) executed, output: {byte_data!r}")
        
        # Use default_serializer.unpack_serializable
        # It returns (instance, offset), we need the instance
        new_instance, offset = default_serializer.unpack_serializable(SimplePayload, byte_data)
        print(f"SimplePayload.from_bytes() (via default_serializer) executed, new instance: {new_instance}, offset: {offset}")
        assert new_instance.some_data == 123
        print("Serialization and deserialization of SimplePayload successful using default_serializer.")
        return True

    except Exception as e:
        print(f"Error during SimplePayload to_bytes/from_bytes using default_serializer: {e}")
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    move_data_passed = test_move_data_serialization()
    proposed_block_passed = test_proposed_block_payload_serialization()
    dataclass_payload_passed = test_dataclass_payload_methods()

    if move_data_passed and proposed_block_passed and dataclass_payload_passed:
        print("\nAll model tests PASSED!")
    else:
        print("\nSome model tests FAILED.")
