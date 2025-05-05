# KKL199

## 👥 Team Members

- Levan Dalbashvili  
- Irakli Kereleishvili  
- Giorgi Kurtanidze  

## 🧠 Decentralized Chess Rating System – Architecture (Text-Based)

```plaintext
+--------------------------+
|      User Device         |
|--------------------------|
| - Game Fetcher (API)     |
| - LMDB Game Store        |
| - DID (Identity)         |
| - Signature Engine       |
|                          |
| 1. Fetch game history    |
| 2. Store in LMDB         |
| 3. Sign game data        |
+-----------+--------------+
            |
            v
+--------------------------+
|   IPv8 Overlay Network   |   <-- P2P layer
|--------------------------|
| - Peer Discovery         |
| - Gossip Protocol        |
| - DHT Key-Value Store    |
|                          |
| 4. Publish (key, value)  |
| 5. Gossip data to peers  |
+-----------+--------------+
            |
            v
+--------------------------+
|        Peers             |
|--------------------------|
| - Fetch data from DHT    |
| - Verify signatures      |
| - Cache game histories   |
+-----------+--------------+
            |
            v
+--------------------------+
|       Blockchain         |
|--------------------------|
| - Merkle root anchor     |
| - Integrity guarantee    |
+--------------------------+
```

This updated architecture diagram is now formatted in a clean and visually appealing way using a code block for better readability.

![image](https://github.com/user-attachments/assets/80845a45-9eb5-455c-a28e-69ffc1c14af8)

