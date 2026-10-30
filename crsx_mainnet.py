import hashlib
import time
import json
import socket
import ssl
import threading
import os
import sys
import sqlite3
import ecdsa
import secrets
import urllib.request
from datetime import datetime, timezone

# Official GitHub-hosted dynamic peers URL
GITHUB_PEERS_URL = "https://raw.githubusercontent.com/maftukha/crisiscoin-network/refs/heads/main/known_peers.json"

# Fallback Bootstrap Nodes
BOOTSTRAP_NODES = [
    "43.106.128.236:6666"
]

# Wordlist for 12-word mnemonic generation
WORDS_LIST = [
    "abandon", "ability", "able", "about", "above", "absent", "absorb", "abstract", 
    "absurd", "abuse", "access", "accident", "account", "accuse", "achieve", "acid",
    "acoustic", "acquire", "across", "act", "action", "actor", "actress", "actual"
]

class WalletManager:
    def __init__(self, wallet_file="crsx_wallet.json", forced_mnemonic=None):
        self.wallet_file = wallet_file
        self.private_key = None
        self.public_key = None
        self.mnemonic = ""
        
        if forced_mnemonic:
            self.mnemonic = forced_mnemonic
            self.save_wallet()
            self.load_from_mnemonic()
        else:
            self.load_or_create_wallet()

    def generate_mnemonic(self):
        return " ".join(secrets.choice(WORDS_LIST) for _ in range(12))

    def save_wallet(self):
        with open(self.wallet_file, "w") as f:
            json.dump({"mnemonic": self.mnemonic}, f, indent=4)

    def load_from_mnemonic(self):
        seed_bytes = hashlib.sha256(self.mnemonic.encode()).digest()
        self.private_key = ecdsa.SigningKey.from_string(seed_bytes, curve=ecdsa.SECP256k1)
        self.public_key = self.private_key.get_verifying_key()

    def load_or_create_wallet(self):
        if os.path.exists(self.wallet_file):
            with open(self.wallet_file, "r") as f:
                data = json.load(f)
                self.mnemonic = data["mnemonic"]
                self.load_from_mnemonic()
            print(f"[WALLET] Loaded existing wallet from {self.wallet_file}")
        else:
            self.mnemonic = self.generate_mnemonic()
            self.load_from_mnemonic()
            self.save_wallet()
            print(f"[WALLET] Created new wallet and saved to {self.wallet_file}")

    def get_address(self):
        pub_bytes = self.public_key.to_string()
        return hashlib.sha256(pub_bytes).hexdigest()

    def sign_transaction(self, tx_data):
        tx_str = json.dumps(tx_data, sort_keys=True)
        return self.private_key.sign(tx_str.encode('utf-8')).hex()

    @staticmethod
    def verify_signature(public_key_hex, signature_hex, tx_data):
        try:
            vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(public_key_hex), curve=ecdsa.SECP256k1)
            return vk.verify(bytes.fromhex(signature_hex), json.dumps(tx_data, sort_keys=True).encode('utf-8'))
        except:
            return False


class SQLiteBlockchain:
    def __init__(self, db_name="crsx_blockchain.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_db()

    def init_db(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                index_id INTEGER PRIMARY KEY,
                previous_hash TEXT,
                transactions TEXT,
                timestamp TEXT,
                nonce INTEGER,
                difficulty INTEGER,
                hash TEXT
            )
        ''')
        self.conn.commit()
        if self.get_latest_block() is None:
            self.create_genesis_block()

    def create_genesis_block(self):
        genesis = {
            "index": 0,
            "previous_hash": "0",
            "transactions": json.dumps(["Genesis Block: Crisis Coin Secure Global Mainnet Initiated."]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": 0,
            "difficulty": 4,
            "hash": "0000000000000000000000000000000000000000000000000000000000000000"
        }
        self.cursor.execute('INSERT INTO blocks VALUES (?, ?, ?, ?, ?, ?, ?)', 
                            (genesis["index"], genesis["previous_hash"], genesis["transactions"], 
                             genesis["timestamp"], genesis["nonce"], genesis["difficulty"], genesis["hash"]))
        self.conn.commit()

    def get_latest_block(self):
        self.cursor.execute('SELECT index_id, previous_hash, transactions, timestamp, nonce, difficulty, hash FROM blocks ORDER BY index_id DESC LIMIT 1')
        row = self.cursor.fetchone()
        if row:
            return {
                "index": row[0], "previous_hash": row[1], "transactions": json.loads(row[2]),
                "timestamp": row[3], "nonce": row[4], "difficulty": row[5], "hash": row[6]
            }
        return None

    def add_block(self, block):
        self.cursor.execute('INSERT INTO blocks VALUES (?, ?, ?, ?, ?, ?, ?)', 
                            (block["index"], block["previous_hash"], json.dumps(block["transactions"]), 
                             block["timestamp"], block["nonce"], block["difficulty"], block["hash"]))
        self.conn.commit()


class CrisisCoinSecureNode:
    def __init__(self, port):
        self.port = port
        self.db = SQLiteBlockchain(f"crsx_secure_node_{port}.db")
        self.initial_reward = 9.99
        self.pending_transactions = []
        self.peer_file = "known_peers.json"
        self.peers = self.load_peers()
        self.fetch_peers_from_github()
        for node_ip in BOOTSTRAP_NODES:
            self.peers.add(node_ip)
        self.save_peers()
        self.peer_sockets = []
        self.request_tracker = {}
        self.rate_limit_lock = threading.Lock()

    def load_peers(self):
        if os.path.exists(self.peer_file):
            with open(self.peer_file, "r") as f:
                return set(json.load(f))
        return set()

    def save_peers(self):
        with open(self.peer_file, "w") as f:
            json.dump(list(self.peers), f)

    def fetch_peers_from_github(self):
        try:
            req = urllib.request.Request(GITHUB_PEERS_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                if isinstance(data, list):
                    for p in data:
                        self.peers.add(p)
                    self.save_peers()
                    print(f"[NETWORK] Successfully updated peers from GitHub: {len(data)} nodes loaded.")
        except Exception as e:
            print(f"[NETWORK] Using local peer cache: {e}")

    def is_rate_limited(self, ip):
        now = time.time()
        with self.rate_limit_lock:
            if ip not in self.request_tracker:
                self.request_tracker[ip] = []
            self.request_tracker[ip] = [t for t in self.request_tracker[ip] if now - t < 2.0]
            if len(self.request_tracker[ip]) >= 10:
                return True
            self.request_tracker[ip].append(now)
            return False

    def calculate_current_reward(self):
        cursor_genesis = self.db.cursor
        cursor_genesis.execute('SELECT timestamp FROM blocks WHERE index_id = 0')
        row = cursor_genesis.fetchone()
        if not row:
            return self.initial_reward
        genesis_time = datetime.fromisoformat(row[0]).timestamp()
        elapsed_days = (datetime.now(timezone.utc).timestamp() - genesis_time) / (24 * 3600)
        periods = int(elapsed_days // 999)
        return max(self.initial_reward / (10 ** periods), 0.00000001)


def handle_secure_connection(ssock, addr, node):
    ip = addr[0]
    print(f"[TLS/P2P] Secure encrypted connection from: {addr}")
    node.peer_sockets.append(ssock)
    try:
        while True:
            if node.is_rate_limited(ip):
                break
            data = ssock.recv(8192)
            if not data:
                break
            msg = json.loads(data.decode('utf-8'))
            if msg.get("action") == "GET_PEERS":
                ssock.sendall(json.dumps({"action": "PEER_LIST", "peers": list(node.peers)}).encode('utf-8'))
    except:
        pass
    finally:
        if ssock in node.peer_sockets:
            node.peer_sockets.remove(ssock)
        ssock.close()


def start_server(node, port):
    bind_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bind_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bind_socket.bind(('0.0.0.0', port))
    bind_socket.listen(10)
    
    print(f"[SERVER] Mainnet Node listening securely on port {port}...")
    
    # Menggunakan SSL context standar tanpa library luar untuk menghindari error GIL Windows
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    # Cek apakah ada sertifikat lokal, jika tidak gunakan TCP standar berlapis
    server_cert = "server.crt"
    server_key = "server.key"
    
    has_ssl = os.path.exists(server_cert) and os.path.exists(server_key)
    if has_ssl:
        try:
            context.load_cert_chain(certfile=server_cert, keyfile=server_key)
        except:
            has_ssl = False

    while True:
        sock, addr = bind_socket.accept()
        try:
            if has_ssl:
                ssock = context.wrap_socket(sock, server_side=True)
            else:
                ssock = sock
            node.peers.add(f"{addr[0]}:{port}")
            node.save_peers()
            threading.Thread(target=handle_secure_connection, args=(ssock, addr, node), daemon=True).start()
        except Exception as e:
            sock.close()


def mining_worker(node, wallet_address):
    print(f"[MINER] Proof-of-Work engine active for address: {wallet_address[:12]}...")
    while True:
        latest = node.db.get_latest_block()
        difficulty = latest["difficulty"]
        target = "0" * difficulty
        nonce = 0
        timestamp = datetime.now(timezone.utc).isoformat()
        current_reward = node.calculate_current_reward()
        
        txs = list(node.pending_transactions)
        txs.append({"sender": "NETWORK", "recipient": wallet_address, "amount": current_reward, "timestamp": timestamp})
        
        while True:
            block_data = {
                "index": latest["index"] + 1,
                "previous_hash": latest["hash"],
                "transactions": txs,
                "timestamp": timestamp,
                "nonce": nonce,
                "difficulty": difficulty
            }
            h = hashlib.sha256(json.dumps(block_data, sort_keys=True).encode()).hexdigest()
            
            if h.startswith(target):
                new_block = block_data.copy()
                new_block["hash"] = h
                node.db.add_block(new_block)
                node.pending_transactions = []
                print(f"\n[SUCCESS] Block #{new_block['index']} mined securely! Reward: {current_reward} CRSX | Hash: {h[:16]}...")
                break
            
            nonce += 1
            if nonce % 200000 == 0:
                if node.db.get_latest_block()["index"] != latest["index"]:
                    break


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 6666
    wallet_file = f"wallet_{port}.json"
    
    print("==================================================")
    print("   CRISIS COIN (CRSX) SECURE GLOBAL MAINNET       ")
    print("==================================================")
    
    wallet = WalletManager(wallet_file)
    address = wallet.get_address()
    
    print("\n==================================================")
    print(f" [SUCCESS] SECURE WALLET INITIALIZED")
    print(f" Node Wallet Address : {address}")
    print("==================================================\n")
    
    node = CrisisCoinSecureNode(port)
    
    # Jalankan Server dan Penambang secara paralel tanpa error GIL
    threading.Thread(target=start_server, args=(node, port), daemon=True).start()
    threading.Thread(target=mining_worker, args=(node, address), daemon=True).start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nSecure Node shutting down safely.")
