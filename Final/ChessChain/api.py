#!/usr/bin/env python3
"""REST API for ChessChain blockchain.

This module provides a REST API interface to interact with the ChessChain blockchain.
"""
import os
import sys
import asyncio
import json
import base64
import hashlib
import uvicorn
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add the current directory to the path to allow imports from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Blockchain imports
from ipv8_service import IPv8
from config.config import create_ipv8_config
from community.community import ChessCommunity
from models.models import ChessTransaction, MoveData
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

# Create FastAPI app
app = FastAPI(
    title="ChessChain API",
    description="REST API for interacting with the ChessChain blockchain",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
ipv8_instance = None
chess_community = None

# Pydantic models for API
class Health(BaseModel):
    status: str
    version: str
    connected_peers: int

class MoveRequest(BaseModel):
    game_id: str
    move_number: int
    from_square: str
    to_square: str
    piece: str
    promotion: Optional[str] = None
    player_public_key: str
    signature: str

class VerifyRequest(BaseModel):
    move_data: dict
    signature: str
    public_key: str

class VerifyResponse(BaseModel):
    valid: bool

class GameHistoryResponse(BaseModel):
    game_id: str
    moves: List[dict]
    verified: bool

# API endpoints
@app.get("/health")
async def health():
    """Health check endpoint"""
    if chess_community is None:
        return {"status": "initializing", "version": "1.0.0", "connected_peers": 0}
    
    return {
        "status": "ok",
        "version": "1.0.0",
        "connected_peers": len(chess_community.get_peers())
    }

@app.post("/moves", status_code=201)
async def submit_move(move_request: MoveRequest):
    """Submit a move to the blockchain"""
    if chess_community is None:
        raise HTTPException(status_code=503, detail="Blockchain not initialized")
    
    try:
        # Check if public key is in base64 or hex format
        public_key_bytes = None
        signature_bytes = None
        
        # Try base64 decode first
        if '=' in move_request.player_public_key or not all(c in '0123456789abcdefABCDEF' for c in move_request.player_public_key.replace('0x', '')):
            try:
                public_key_bytes = base64.b64decode(move_request.player_public_key)
                signature_bytes = base64.b64decode(move_request.signature)
                print("Using base64 decoded keys for move submission")
            except Exception as e:
                print(f"Base64 decode failed: {e}")
        
        # Try hex decode if base64 failed
        if public_key_bytes is None:
            try:
                public_key_bytes = bytes.fromhex(move_request.player_public_key.replace("0x", ""))
                signature_bytes = bytes.fromhex(move_request.signature.replace("0x", ""))
                print("Using hex decoded keys for move submission")
            except Exception as e:
                print(f"Hex decode failed: {e}")
                raise HTTPException(status_code=400, detail=f"Invalid key format: {str(e)}")
        
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        
        # Create the move data
        move_data = {
            "game_id": move_request.game_id,
            "move_number": move_request.move_number,
            "from_square": move_request.from_square,
            "to_square": move_request.to_square,
            "piece": move_request.piece,
            "promotion": move_request.promotion
        }
        
        # Verify signature
        message_bytes = json.dumps(move_data, sort_keys=True).encode('utf-8')
        
        # Verify signature
        try:
            public_key.verify(signature_bytes, message_bytes)
        except InvalidSignature:
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Create MoveData object
        move = MoveData(
            id=f"{move_request.game_id}_{move_request.move_number}",
            match_id=move_request.game_id,
            move_number=move_request.move_number,
            from_square=move_request.from_square,
            to_square=move_request.to_square,
            piece=move_request.piece,
            promotion=move_request.promotion if move_request.promotion else "",
            player_pubkey=move_request.player_public_key,
            signature=move_request.signature
        )
        
        # Send move to the blockchain
        # This is async but we don't need to await it
        asyncio.create_task(chess_community.broadcast_move(move))
        
        return {"success": True, "message": "Move submitted to blockchain"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error submitting move: {str(e)}")

@app.post("/verify", response_model=VerifyResponse)
async def verify_signature(verify_request: VerifyRequest):
    """Verify a move signature using Ed25519"""
    try:
        # Convert move data to bytes
        message_string = json.dumps(verify_request.move_data, sort_keys=True)
        message_bytes = message_string.encode('utf-8')
        
        # Process signature
        try:
            # Check if signature is in base64 or hex format
            signature_bytes = None
            public_key_bytes = None
            
            # Try base64 decode first
            if '=' in verify_request.signature or not all(c in '0123456789abcdefABCDEF' for c in verify_request.signature.replace('0x', '')):
                try:
                    signature_bytes = base64.b64decode(verify_request.signature)
                    public_key_bytes = base64.b64decode(verify_request.public_key)
                    print("Using base64 decoded keys")
                except Exception as e:
                    print(f"Base64 decode failed: {e}")
            
            # Try hex decode if base64 failed
            if signature_bytes is None:
                try:
                    signature_bytes = bytes.fromhex(verify_request.signature.replace('0x', ''))
                    public_key_bytes = bytes.fromhex(verify_request.public_key.replace('0x', ''))
                    print("Using hex decoded keys")
                except Exception as e:
                    print(f"Hex decode failed: {e}")
                    return {"valid": False}
            
            # Load the Ed25519 public key
            public_key_obj = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            # Verify signature
            try:
                public_key_obj.verify(signature_bytes, message_bytes)
                return {"valid": True}
            except InvalidSignature:
                print("Ed25519 signature verification failed")
                return {"valid": False}
                
        except Exception as e:
            print(f"Ed25519 signature processing error: {e}")
            return {"valid": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying signature: {str(e)}")

@app.get("/games/{game_id}", response_model=GameHistoryResponse)
async def get_game_history(game_id: str):
    """Get the move history for a game from the blockchain"""
    if chess_community is None:
        raise HTTPException(status_code=503, detail="Blockchain not initialized")
    
    try:
        # Get moves from the blockchain
        moves = chess_community.get_stored_moves(game_id)
        
        # Convert to API format
        move_list = []
        for move in moves:
            move_list.append({
                "move_number": move.move_number,
                "from_square": move.from_square,
                "to_square": move.to_square,
                "piece": move.piece,
                "promotion": move.promotion if move.promotion else None,
                "player_public_key": move.player_pubkey,
                "signature": move.signature
            })
        
        return {
            "game_id": game_id,
            "moves": move_list,
            "verified": True  # We could implement additional verification here
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching game history: {str(e)}")

# Function to initialize the blockchain
async def initialize_blockchain(port: int):
    """Initialize the blockchain in the background"""
    global ipv8_instance, chess_community
    
    try:
        # Create and initialize IPv8 with the chess community
        ipv8_instance = IPv8(
            create_ipv8_config(port), 
            extra_communities={'ChessCommunity': ChessCommunity}
        )
        
        # Start IPv8 service
        await ipv8_instance.start()
        
        # Get reference to our chess community
        chess_community = ipv8_instance.get_overlay(ChessCommunity)
        print(f"ChessChain initialized: {chess_community.my_peer}")
    except Exception as e:
        print(f"Error initializing blockchain: {str(e)}")

# Background task to start the blockchain
@app.on_event("startup")
async def startup_event():
    """Start the blockchain when the API starts"""
    # Start blockchain in port 8000 by default
    asyncio.create_task(initialize_blockchain(8000))

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the blockchain when the API stops"""
    global ipv8_instance
    if ipv8_instance:
        await ipv8_instance.stop()

# Main entry point
if __name__ == "__main__":
    # Get port from command line
    import argparse
    parser = argparse.ArgumentParser(description="ChessChain API")
    parser.add_argument("--port", type=int, default=8080, help="API port")
    parser.add_argument("--blockchain-port", type=int, default=8000, help="Blockchain port")
    args = parser.parse_args()
    
    # Ensure chess_db directory exists
    os.makedirs("chess_db", exist_ok=True)
    
    # Start API server
    print(f"Starting ChessChain API on port {args.port}")
    uvicorn.run("api:app", host="0.0.0.0", port=args.port, reload=False)
