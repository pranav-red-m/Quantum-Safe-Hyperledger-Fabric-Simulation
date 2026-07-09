import os
import sys

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import time
import pandas as pd
import requests

from security.kem_client import KEMClient
from security.aes_session import (
    derive_session_key,
    encrypt_packet
)


EDGE_URL = "http://localhost:5001/scan"

DATASET = "dataset/CICIOT23/train/train.csv"

DEVICES = [
    "camera01",
    "doorlock01",
    "motionsensor01",
    "thermostat01",
    "smartplug01"
]

WINDOW_SIZE = 5

# Where per-request results are logged for benchmark analysis
RESULTS_LOG = "results_log.jsonl"

# Initialize PQC Client
kem_client = KEMClient()

print("\n[IOT] Loading Dataset...")

df = pd.read_csv(DATASET)

print(f"[IOT] Dataset Shape = {df.shape}")

# ==========================================
# SELECT TEST SET
# ==========================================

benign_df = df[
    df["label"] == "BenignTraffic"
].sample(
    n=30,
    random_state=42
)

attack_df = df[
    df["label"] != "BenignTraffic"
].sample(
    n=20,
    random_state=42
)

test_df = pd.concat(
    [
        benign_df,
        attack_df
    ]
).sample(
    frac=1,
    random_state=42
).reset_index(
    drop=True
)

print(f"[IOT] Total Test Packets = {len(test_df)}")

# ==========================================
# FEATURES
# ==========================================

FEATURE_COLUMNS = [
    col
    for col in test_df.columns
    if col != "label"
]

print(f"[IOT] Feature Count = {len(FEATURE_COLUMNS)}")

# ==========================================
# RUN-LEVEL COUNTERS (for end-of-run summary)
# ==========================================

total_requests = 0
total_blockchain_committed = 0
total_blockchain_failed = 0
total_blockchain_skipped = 0  # benign packets never touch the chain
end_to_end_latencies = []
blockchain_latencies = []

# ==========================================
# SEND SLIDING WINDOWS
# ==========================================

for i in range(WINDOW_SIZE - 1, len(test_df)):

    # Create sliding window
    window = (
        test_df[FEATURE_COLUMNS]
        .iloc[
            i - WINDOW_SIZE + 1 : i + 1
        ]
        .values
        .tolist()
    )

    device_id = DEVICES[
        i % len(DEVICES)
    ]

    actual_label = test_df.iloc[i]["label"]

    packet = {

        "device_id": device_id,

        "packet_window": window,

        "actual_label": actual_label

    }

    try:

        print("\n==============================")
        print("        IoT Device")
        print("==============================")

        print(f"Device : {device_id}")

        print("\nCreating Telemetry Packet...")
        print("SUCCESS")

        print("\nObtaining Edge Public Key...")

        kem_ciphertext, shared_secret, kem_time = kem_client.encapsulate()

        print("SUCCESS")

        print(f"\nML-KEM Encapsulation Time : {kem_time:.3f} ms")
        print("SUCCESS")

        session_key = derive_session_key(
            shared_secret
        )

        print("\nShared Secret Established")
        print("SUCCESS")

        nonce, ciphertext = encrypt_packet(
            packet,
            session_key
        )

        print("\nAES-256-GCM Encryption...")
        print("SUCCESS")

        print(f"\nEncrypted Packet Size : {len(ciphertext)} bytes")
        print(f"Nonce Size            : {len(nonce)} bytes")
        print(f"KEM Ciphertext Size   : {len(kem_ciphertext)} bytes")

        secure_payload = {

            "device_id": device_id,

            "kem_ciphertext": kem_ciphertext.hex(),

            "nonce": nonce.hex(),

            "ciphertext": ciphertext.hex()

        }

        print("\nSending Secure Packet...")
        print("SUCCESS")

        request_start = time.perf_counter()

        response = requests.post(

            EDGE_URL,

            json=secure_payload,

            timeout=30

        )

        end_to_end_ms = (time.perf_counter() - request_start) * 1000

        result = response.json()

        print()

        print(
            f"[{device_id}]",
            result
        )

        # ==========================================
        # BLOCKCHAIN RESULT REPORTING
        # ==========================================

        blockchain_status = result.get("blockchain_status")
        blockchain_tx_id = result.get("blockchain_tx_id")

        total_requests += 1
        end_to_end_latencies.append(end_to_end_ms)

        print("\n==================================================")
        print("BLOCKCHAIN RESULT (as reported by edge gateway)")
        print("==================================================")

        if blockchain_status == "committed":
            total_blockchain_committed += 1
            print(f"Status : COMMITTED")
            print(f"Tx ID  : {blockchain_tx_id}")
        elif blockchain_status == "failed":
            total_blockchain_failed += 1
            print(f"Status : FAILED")
        else:
            # benign packets never reach the blockchain code path
            total_blockchain_skipped += 1
            print("Status : SKIPPED (benign traffic, not anchored on-chain)")

        print(f"End-to-End Latency : {end_to_end_ms:.3f} ms")

        # ==========================================
        # STRUCTURED LOG LINE (for later analysis)
        # ==========================================

        log_entry = {
            "timestamp": time.time(),
            "device_id": device_id,
            "actual_label": actual_label,
            "predicted_status": result.get("status"),
            "threat_score": result.get("score"),
            "reconstruction_error": result.get("reconstruction_error"),
            "end_to_end_latency_ms": end_to_end_ms,
            "blockchain_status": blockchain_status,
            "blockchain_tx_id": blockchain_tx_id,
        }

        with open(RESULTS_LOG, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    except requests.exceptions.ConnectionError:

        print("\n[ERROR] Edge Gateway is Offline.")
        print("Please start edge_gateway.py")
        break

    except KeyboardInterrupt:

        print("\n==============================")
        print(" IoT Simulation Stopped ")
        print("==============================")
        break

    except Exception as e:

        print("[IOT ERROR]", str(e))
        break

    time.sleep(1)

# ==========================================
# END-OF-RUN SUMMARY
# ==========================================

print()
print("==============================")
print(" IoT Simulation Completed ")
print("==============================")

print("\n==================================================")
print("RUN SUMMARY")
print("==================================================")
print(f"Total Requests             : {total_requests}")
print(f"Blockchain Committed       : {total_blockchain_committed}")
print(f"Blockchain Failed          : {total_blockchain_failed}")
print(f"Blockchain Skipped (benign): {total_blockchain_skipped}")

if end_to_end_latencies:
    import statistics
    print(f"\nEnd-to-End Latency (ms)")
    print(f"  mean   : {statistics.mean(end_to_end_latencies):.2f}")
    print(f"  median : {statistics.median(end_to_end_latencies):.2f}")
    print(f"  min    : {min(end_to_end_latencies):.2f}")
    print(f"  max    : {max(end_to_end_latencies):.2f}")
    if len(end_to_end_latencies) > 1:
        print(f"  stdev  : {statistics.stdev(end_to_end_latencies):.2f}")

print(f"\nFull per-request log written to: {RESULTS_LOG}")