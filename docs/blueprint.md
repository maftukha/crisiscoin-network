---

# Crisis Coin (CRSX) - Technical Blueprint & Specification

## 1. Overview & Objectives

Crisis Coin (CRSX) is a secure, decentralized, and lightweight Proof-of-Work (PoW) blockchain network built natively in Python. Designed to run seamlessly on Windows and Linux VPS infrastructure, CRSX eliminates heavy external dependencies (such as native OpenSSL binaries) by utilizing Python-native cryptographic libraries and robust TLS/SSL encapsulation.

---

## 2. Core Architecture & Components

### A. Cryptographic Wallet & Security (`WalletManager`)

* **Mnemonic Seed Generation:** Utilizes a secure 12-word recovery phrase derived from a standardized wordlist using cryptographically secure pseudo-random number generation (`secrets`).
* **Asymmetric Cryptography:** Employs the `ecdsa` library with the `SECP256k1` curve (the same curve used by Bitcoin) for signing and verifying transactions.
* **Persistent Local Storage:** Automatically detects and loads existing local wallets (e.g., `wallet_6666.json`) to prevent accidental fund or identity loss during restarts.

### B. Storage & Persistence (`SQLiteBlockchain`)

* **Database Backend:** Powered by SQLite (`crsx_blockchain.db`), ensuring atomic transactions, durability, and low memory overhead.
* **Block Structure:** Each block contains an index, previous hash, transactions payload, UTC timestamp, nonce, difficulty target, and current cryptographic hash.
* **Genesis Initialization:** Automatically provisions a secure Genesis Block upon initial deployment.

### C. Network & Peer Discovery (`CrisisCoinSecureNode`)

* **Dynamic GitHub Peer Fetching:** Automatically pulls the latest active node list from a publicly hosted GitHub repository (`known_peers.json`), ensuring the network remains operational even if VPS IP addresses change.
* **Encrypted P2P Transport:** Wraps standard TCP sockets in TLS/SSL using self-signed certificates generated dynamically via Python's `cryptography` library.
* **DDoS Mitigation:** Features built-in IP rate-limiting to protect nodes against request spamming and connection flooding.

---

## 3. Tokenomics & Mining Engine

* **Consensus Mechanism:** Proof-of-Work (PoW) utilizing SHA-256 hashing with adjustable difficulty targets.
* **Initial Reward Structure:** The Genesis Mining phase issues an initial reward of **9.99 CRSX** per successfully mined block.
* **Halving / Decay Model:** Dynamic reward decay calculation based on elapsed time periods relative to the Genesis block timestamp.

---

## 4. Network Resilience & Failover Strategy

1. **GitHub-Hosted Seed List:** Primary discovery relies on a centralized JSON registry on GitHub, allowing instant network updates without requiring code redistribution.
2. **Local Peer Caching:** Nodes cache known peers locally. If GitHub is unreachable, the node falls back to its local peer list and hardcoded backup bootstrap nodes.
3. **Multi-Node Deployment:** VPS operators can easily spin up backup nodes and update the GitHub `known_peers.json` file to maintain uninterrupted global consensus.
