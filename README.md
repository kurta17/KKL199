# KKL199

## 👥 Team Members

- Levan Dalbashvili  
- Irakli Kereleishvili  
- Giorgi Kurtanidze  

## 🧠 Decentralized Chess Rating System – Architecture (Text-Based)

```plaintext

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! Platform Side !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
[User Registration]
   |
   v
[Input Username (chess.com or lichess.org)]
   |
   v
[System Queries API to Verify Username]
   |
   |--[If Valid]--> [Generate Private/Public Key Pair for User]
   |                |
   |                v
   |                [Store in LMDB: User Data (Username, Platform, Public Key, Initial Rating)]
   |                |
   |                v
   |                [Trigger Function: Send Welcome Notification to User]
   |
   |--[If Invalid]--> [Error: "Username Not Found, Cannot Register"]
   |
   |
[Match Played]
   |
   v
[Match Agreement at the end]
   |
   v
   |
   v
[Both Sign Agreement: "I won/lose" with Private Keys]
   |
   v

   |
[Store in LMDB: Match Agreement (Match ID, Player1, Player2, Signatures(both or one), Moves, Timestamp)]
   |              
   |
   |
   v
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! Network side !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
   |
   |
[Peer gets data from LMDB]
   |
   |
Peers verify the signatures of the win/lose message
   |
   |
Makes a transaction for one match
   |
   |
broadcast to other peers

 Valid TX → PoS mempool
   |
   │
   ↓
PoS consensus:
      ├─ Proposer election ∝ stake  !!!!!
      ├─ Block proposal (TXs + Merkle root) !!!!!
      └─ Validator voting/quorum !!!!!
      |
      ↓
Finalized block → push‑gossip
      |
      ↓
Peers validate & append block
      
```
