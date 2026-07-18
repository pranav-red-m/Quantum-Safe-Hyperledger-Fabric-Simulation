import argparse
import os
import sys
import uuid

import pandas as pd
import requests
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from security.kem_client import KEMClient
from security.aes_session import derive_session_key, encrypt_packet, generate_hmac
from shared.config import EDGE_PORT

EDGE_URL = f"http://localhost:{EDGE_PORT}/scan"
DATASET = "dataset/CICIOT23/test/test.csv"

DEVICES = [
    "camera01",
    "doorlock01",
    "motionsensor01",
    "thermostat01",
    "smartplug01",
]

WINDOW_SIZE = 10

ATTACK_PREDICTIONS = {
    "temporary_isolation",
    "permanent_block",
    "reject",
    "attack",
}

BLOCKCHAIN_COMMITTED_STATUSES = {"committed"}
BLOCKCHAIN_FAILURE_STATUSES = {
    "failed",
    "finalize_failed",
    "commit_failed",
    "finalize_unreachable",
    "unverified",
    "invalid_signature",
}


def parse_arguments():
    parser = argparse.ArgumentParser(description="Edge/Cloud end-to-end functional test")
    parser.add_argument(
        "--packets", type=int, default=10,
        help="Number of packets to send (default: 10, for a quick smoke test)",
    )
    parser.add_argument(
        "--random-state", type=int, default=42,
        help="Random seed for dataset sampling",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    packet_count = arguments.packets

    print("[IOT] Loading Test Dataset...")
    dataframe = pd.read_csv(DATASET).reset_index(drop=True)

    # Sample enough rows to build `packet_count` sliding windows
    sample_size = packet_count + WINDOW_SIZE - 1
    dataframe = dataframe.sample(
        n=min(sample_size, len(dataframe)),
        random_state=arguments.random_state,
    ).reset_index(drop=True)

    feature_columns = [c for c in dataframe.columns if c != "label"]

    actual_labels = []
    predicted_labels = []

    blockchain_committed = 0
    blockchain_pending = 0
    blockchain_failed = 0
    blockchain_not_attempted = 0
    blockchain_unknown = 0

    kem_client = KEMClient()

    print(f"\nTesting on {len(dataframe) - WINDOW_SIZE + 1} rows...")
    print(f"Window Size: {WINDOW_SIZE}\n")

    for i in range(WINDOW_SIZE - 1, len(dataframe)):

        window = dataframe[feature_columns].iloc[i - WINDOW_SIZE + 1:i + 1].values.tolist()

        actual_label = dataframe.iloc[i]["label"]

        packet = {"packet_window": window}

        try:
            kem_ciphertext, shared_secret, _ = kem_client.encapsulate()

            # Per-session id binds the derived key + HMAC to this exchange
            session_id = uuid.uuid4().hex
            session_key = derive_session_key(shared_secret, session_id.encode())

            nonce, ciphertext = encrypt_packet(packet, session_key)

            authentication_tag = generate_hmac(session_key, session_id, ciphertext)

            payload = {
                "device_id": DEVICES[i % len(DEVICES)],
                "session_id": session_id,
                "status": "ACTIVE",
                "attack_count": 0,
                "kem_ciphertext": kem_ciphertext.hex(),
                "ciphertext": ciphertext.hex(),
                "nonce": nonce.hex(),
                "auth_tag": authentication_tag.hex(),
                "actual_label": actual_label,
            }

            response = requests.post(EDGE_URL, json=payload, timeout=15)
            result = response.json()

            predicted_status = result.get("status", "").lower()

            if actual_label == "BenignTraffic":
                actual_labels.append("Benign")
            else:
                actual_labels.append("Attack")

            if predicted_status in ATTACK_PREDICTIONS:
                predicted_labels.append("Attack")
            else:
                predicted_labels.append("Benign")

            blockchain_status = result.get("blockchain_status")
            blockchain_block_id = result.get("blockchain_block_id")

            if blockchain_status in BLOCKCHAIN_COMMITTED_STATUSES:
                blockchain_committed += 1
            elif blockchain_status == "pending":
                blockchain_pending += 1
            elif blockchain_status in BLOCKCHAIN_FAILURE_STATUSES:
                blockchain_failed += 1
            elif blockchain_status in (None, "not_attempted"):
                blockchain_not_attempted += 1
            else:
                blockchain_unknown += 1

            blockchain_note = ""
            if blockchain_status:
                blockchain_note = f"  Chain: {blockchain_status}"
                if blockchain_block_id:
                    blockchain_note += f" ({blockchain_block_id})"

            print(
                f"[{i - WINDOW_SIZE + 2}/{len(dataframe) - WINDOW_SIZE + 1}]",
                payload["device_id"],
                "GT:", actual_labels[-1],
                "Pred:", predicted_labels[-1],
                blockchain_note,
            )

        except Exception as error:
            print(f"[ERROR] Packet {i}: {error}")

    print("\n==================================================")
    print("IDS CLASSIFICATION RESULTS")
    print("==================================================")

    if actual_labels:
        print(f"Accuracy: {accuracy_score(actual_labels, predicted_labels):.4f}\n")
        print(classification_report(actual_labels, predicted_labels))
        print("Confusion Matrix (rows=actual, cols=predicted, labels=[Attack, Benign]):")
        print(confusion_matrix(actual_labels, predicted_labels, labels=["Attack", "Benign"]))
    else:
        print("No packets were successfully processed.")

    print("\n==================================================")
    print("BLOCKCHAIN COMMIT RESULTS")
    print("==================================================")
    attack_packets_sent = predicted_labels.count("Attack")
    print(f"Attacks flagged by IDS      : {attack_packets_sent}")
    print(f"Committed to blockchain     : {blockchain_committed}")
    print(f"Pending (not yet finalized) : {blockchain_pending}")
    print(f"Failed / rejected           : {blockchain_failed}")
    print(f"Not attempted (benign)      : {blockchain_not_attempted}")
    if blockchain_unknown:
        print(f"Unknown status              : {blockchain_unknown}")

    if attack_packets_sent > 0:
        commit_rate = blockchain_committed / attack_packets_sent * 100
        print(f"\nCommit success rate on flagged attacks: {commit_rate:.1f}%")

    print("==================================================")


if __name__ == "__main__":
    main()