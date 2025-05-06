# KKL199

## 👥 Team Members

- Levan Dalbashvili  
- Irakli Kereleishvili  
- Giorgi Kurtanidze  

## 🧠 Decentralized Chess Rating System – Architecture (Text-Based)

```plaintext
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

[Match Agreement In the beginning]
   |
   v
[Two Users Agree to Play via Platform Interface]
   |
   v
[Both Sign Agreement: "I agree to play Match ID: XYZ" with Private Keys]
   |
   v
[System Verifies Signatures Using Public Keys from LMDB]
   |
   |--[If Valid]--> [Store in LMDB: Match Agreement (Match ID, Player1, Player2, Signatures, Timestamp)]
   |                |
   |                v
   |                [Trigger Function: Notify Players to Start Match on chess.com/lichess.org]
   |
   |--[If Invalid]--> [Error: "Invalid Signatures, Agreement Failed"]

[Match Played]
   |
   v
[Users play a Match on chess.com or lichess.org]
   |
   v
[Fetch match moves from website, Run function which identifies the Winner and signsthe  result]
[Nodes Fetch Match Result via API (Win/Loss/Draw, Match ID)]
   |
   v
[Cross-Check Result with LMDB Match Agreement]
   |
   |--[If Valid]--> [Trigger Function: Calculate Rating Changes]
   |                |
   |                v
   |                [Use Elo Formula: Compute New Ratings (e.g., Player1: +12, Player2: -12)]
   |                |
   |                v
   |                [Store in LMDB: Transaction Data (Match ID, Rating Changes, Timestamp)]
   |                |
   |                v
   |                [Trigger Function: Submit Transaction to Mempool]
   |
   |--[If Invalid]--> [Error: "Match Data Mismatch, Transaction Rejected"]

[Transaction Processing]
   |
   v
[Mempool: Collects Pending Transactions]
   |
   v
[Authority Nodes Select Transactions from Mempool]
   |
   v
[Validate Transactions Against LMDB Data]
   |
   v
[Group Valid Transactions into a Block]
   |
   v
[Create Merkle Tree from Transactions]
   |
   v
[Form Block: Merkle Root, Previous Block Hash, Timestamp]
   |
   v
[Authority Nodes Sign Block (Proof of Authority)]
   |
   v
[Store in LMDB: Block Data (Block Hash, Transactions, Signatures)]
   |
   v
[Add Block to Blockchain]
   |
   v
[Trigger Function: Update LMDB User Ratings with New Ratings from Block]
   |
   v
[Broadcast Updated Blockchain State to All Nodes]

```

<img width="1261" alt="Screenshot 2568-05-07 at 00 16 27" src="https://github.com/user-attachments/assets/e86418e7-c462-4f9d-a0f5-d95e27c5c089" />


