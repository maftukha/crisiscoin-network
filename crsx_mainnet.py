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

# Fallback Bootstrap Nodes (if GitHub is unreachable)
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
    """Manages cryptographic wallet, 12-word recovery mnemonic, and ECDSA signatures."""
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
            print(f"[CRITICAL] SAVE YOUR 12-WORD SEED PHRASE SECURELY:\n-> {self.mnemonic}")

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
    """Robust blockchain storage backed by SQLite."""
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
        self.cursor.execute('''
            INSERT INTO blocks VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (genesis["index"], genesis["previous_hash"], genesis["transactions"], 
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

    def get_chain_length(self):
        self.cursor.execute('SELECT COUNT(*) FROM blocks')
        return self.cursor.fetchone()[0]

    def add_block(self, block):
        self.cursor.execute('''
            INSERT INTO blocks VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (block["index"], block["previous_hash"], json.dumps(block["transactions"]), 
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
        
        # Load from GitHub repository dynamically
        self.fetch_peers_from_github()
        
        # Fallback to local bootstrap nodes if empty
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
        """Automatically fetch latest peer list from GitHub repository."""
        try:
            req = urllib.request.Request(
                GITHUB_PEERS_URL, 
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                if isinstance(data, list):
                    for p in data:
                        self.peers.add(p)
                    self.save_peers()
                    print(f"[NETWORK] Successfully updated peers from GitHub: {len(data)} nodes loaded.")
        except Exception as e:
            print(f"[NETWORK] Failed to fetch peers from GitHub (using local cache): {e}")

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

    def add_transaction(self, sender, recipient, amount, pub_key, signature, broadcast=True):
        tx = {"sender": sender, "recipient": recipient, "amount": amount, "timestamp": datetime.now(timezone.utc).isoformat()}
        if sender != "NETWORK" and not WalletManager.verify_signature(pub_key, signature, tx):
            print("[SECURITY] Transaction rejected: Invalid cryptographic signature!")
            return False
        
        if tx not in self.pending_transactions:
            self.pending_transactions.append(tx)
            print(f"[TX] Verified & Added: {sender[:8]}... -> {recipient[:8]} ({amount} CRSX)")
            if broadcast:
                self.broadcast({"action": "NEW_TX", "tx": tx, "pub_key": pub_key, "signature": signature})
            return True
        return False

    def broadcast(self, message):
        data = json.dumps(message).encode('utf-8')
        for sock in list(self.peer_sockets):
            try:
                sock.sendall(data)
            except:
                self.peer_sockets.remove(sock)


def generate_self_signed_cert(certfile="server.crt", keyfile="server.key"):
    if os.path.exists(certfile) and os.path.exists(keyfile):
        return

    print("[TLS] Generating self-signed SSL certificates via Python...")
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime as dt

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"crisiscoin.network")])
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            dt.datetime.now(dt.timezone.utc)
        ).not_valid_after(
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(u"crisiscoin.network")]),
            critical=False,
        ).sign(private_key, hashes.SHA256())

        with open(keyfile, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))

        with open(certfile, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        print("[TLS] SSL Certificates successfully generated.")
    except ImportError:
        pass


def handle_secure_connection(ssock, addr, node):
    ip = addr[0]
    print(f"[TLS/P2P] Secure encrypted connection established from: {addr}")
    node.peer_sockets.append(ssock)
    try:
        while True:
            if node.is_rate_limited(ip):
                print(f"[SECURITY/DDoS] Rate limit exceeded for IP {ip}. Dropping connection.")
                break

            data = ssock.recv(8192)
            if not data:
                break
            msg = json.loads(data.decode('utf-8'))
            action = msg.get("action")
            
            if action == "GET_PEERS":
                ssock.sendall(json.dumps({"action": "PEER_LIST", "peers": list(node.peers)}).encode('utf-8'))
            elif action == "PEER_LIST":
                for p in msg.get("peers", []):
                    node.peers.add(p)
                node.save_peers()
            elif action == "NEW_TX":
                tx = msg.get("tx")
                node.add_transaction(tx["sender"], tx["recipient"], tx["amount"], msg.get("pub_key"), msg.get("signature"), broadcast=False)
    except:
        pass
    finally:
        if ssock in node.peer_sockets:
            node.peer_sockets.remove(ssock)
        ssock.close()


def start_secure_server(node, port):
    server_cert = "server.crt"
    server_key = "server.key"
    
    generate_self_signed_cert(server_cert, server_key)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if os.path.exists(server_cert) and os.path.exists(server_key):
        context.load_cert_chain(certfile=server_cert, keyfile=server_key)
    else:
        context.check_hostname = False

    bind_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bind_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bind_socket.bind(('0.0.0.0', port))
    bind_socket.listen(10)
    
    print(f"[SERVER] Secure TLS Mainnet Node listening on port {port}...")
    
    while True:
        sock, addr = bind_socket.accept()
        try:
            ssock = context.wrap_socket(sock, server_side=True)
            node.peers.add(f"{addr[0]}:{port}")
            node.save_peers()
            threading.Thread(target=handle_secure_connection, args=(ssock, addr, node), daemon=True).start()
        except Exception as e:
            print(f"[TLS ERROR] Handshake failed from {addr}: {e}")
            sock.close()


def connect_to_peers(node):
    """Attempt connection to known network peers."""
    for peer in list(node.peers):
        try:
            ip, port = peer.split(":")
            if ip == "0.0.0.0" or ip == "127.0.0.1":
                continue
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((ip, int(port)))
            print(f"[NETWORK] Connected to peer: {peer}")
            s.close()
        except:
            pass


def mining_worker(node, wallet_address):
    print(f"[MINER] Secure Proof-of-Work engine started for address: {wallet_address[:12]}...")
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
                print(f"\n[SUCCESS] Block #{new_block['index']} mined securely! Reward sent to: {wallet_address[:12]}... Hash: {h[:16]}...")
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
    
    if os.path.exists(wallet_file):
        print(f"[WALLET] Loaded existing wallet from {wallet_file}")
        wallet = WalletManager(wallet_file)
    else:
        print("No wallet found for this node.")
        print("1. Create a New Wallet (Generate 12-word seed)")
        print("2. Import Existing Wallet (Enter 12-word seed phrase)")
        choice = input("Select option (1/2): ").strip()
        if choice == "2":
            mnemonic_input = input("Enter your 12-word seed phrase: ").strip()
            wallet = WalletManager(wallet_file, forced_mnemonic=mnemonic_input)
        else:
            wallet = WalletManager(wallet_file)

    address = wallet.get_address()
    print("\n==================================================")
    print(f" [SUCCESS] SECURE WALLET INITIALIZED")
    print(f" Node Wallet Address : {address}")
    print("==================================================\n")
    
    node = CrisisCoinSecureNode(port)
    
    # Connect to peers retrieved from GitHub
    threading.Thread(target=connect_to_peers, args=(node,), daemon=True).start()
    
    # Start Secure TLS Network Server
    threading.Thread(target=start_secure_server, args=(node, port), daemon=True).start()
    
    # Start Mining Engine
    threading.Thread(target=mining_worker, args=(node, address), daemon=True).start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nSecure Node shutting down safely.")