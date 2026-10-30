#include <WiFi.h>
#include <mbedtls/sha256.h>

// ============================================================================
// CONFIGURATION - UPDATE THESE VALUES BEFORE FLASHING
// ============================================================================
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Node IP (VPS or Local Node) and Port
const char* NODE_IP       = "43.106.128.236";
const uint16_t NODE_PORT  = 6666;

// Miner's CRSX Wallet Address for Receiving Mining Rewards
const char* MINER_WALLET  = "4990d149dae45be6615f45793568ff970bef1273b96055c68db1b98fce872beab";

// ============================================================================
// GLOBAL VARIABLES & UTILITIES
// ============================================================================
WiFiClient client;

// SHA-256 Calculation using ESP32 Hardware Acceleration
String calculateSHA256(const String& input) {
    byte shaResult[32];
    mbedtls_sha256_context ctx;
    mbedtls_sha256_init(&ctx);
    mbedtls_sha256_starts(&ctx, 0); // 0 for SHA-256
    mbedtls_sha256_update(&ctx, (const unsigned char*)input.c_str(), input.length());
    mbedtls_sha256_finish(&ctx, shaResult);
    mbedtls_sha256_free(&ctx);

    char buffer[65];
    for (int i = 0; i < 32; i++) {
        sprintf(buffer + (i * 2), "%02x", shaResult[i]);
    }
    return String(buffer);
}

void connectToWiFi() {
    if (WiFi.status() == WL_CONNECTED) return;
    
    Serial.print("[WiFi] Connecting to ");
    Serial.println(WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\n[WiFi] Connected successfully!");
    Serial.print("[WiFi] ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
}

// ============================================================================
// ARDUINO CORE FUNCTIONS
// ============================================================================
void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n==================================================");
    Serial.println("   CRISIS COIN (CRSX) ESP32 POW MINER v1.0       ");
    Serial.println("==================================================");
    
    connectToWiFi();
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        connectToWiFi();
        return;
    }

    // Connect to CRSX Mainnet Node
    if (!client.connected()) {
        Serial.printf("[NETWORK] Connecting to CRSX Node %s:%d...\n", NODE_IP, NODE_PORT);
        if (!client.connect(NODE_IP, NODE_PORT)) {
            Serial.println("[NETWORK] Connection failed. Retrying in 5 seconds...");
            delay(5000);
            return;
        }
        Serial.println("[NETWORK] Connected to CRSX Node successfully!");
    }

    // Simple PoW Hashing Loop Example
    uint32_t nonce = 0;
    uint32_t startTime = millis();
    uint8_t targetDifficulty = 4; // Target zeros required (0000...)
    String prefixTarget = "";
    for (int i = 0; i < targetDifficulty; i++) prefixTarget += "0";

    String blockDataPrefix = "CRSX_ESP32_BLOCK_DATA_NONCE_";
    
    Serial.println("[MINER] Starting PoW Engine on ESP32 Core...");
    
    while (client.connected()) {
        String dataToHash = blockDataPrefix + String(nonce);
        String hashResult = calculateSHA256(dataToHash);

        if (hashResult.startsWith(prefixTarget)) {
            uint32_t elapsedTime = (millis() - startTime) / 1000;
            float hashRate = (elapsedTime > 0) ? (nonce / (float)elapsedTime) : nonce;
            
            Serial.println("\n[SUCCESS] VALID BLOCK HASH FOUND!");
            Serial.printf(" Nonce    : %u\n", nonce);
            Serial.printf(" Hash     : %s\n", hashResult.c_str());
            Serial.printf(" Hashrate : %.2f H/s\n", hashRate);
            
            // Submit Block to Node
            String payload = "{\"action\":\"SUBMIT_BLOCK\",\"miner\":\"" + String(MINER_WALLET) + "\",\"nonce\":" + String(nonce) + ",\"hash\":\"" + hashResult + "\"}\n";
            client.print(payload);
            break;
        }

        nonce++;
        if (nonce % 10000 == 0) {
            Serial.printf("[MINING] Hashes computed: %u...\n", nonce);
            yield(); // Prevent watchdog timer reset
        }
    }

    delay(3000); // Pause briefly before requesting next job
}
