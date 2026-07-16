import os
import sys
import json
import time
import secrets

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, request, jsonify

from security.verify_signature import verify_packet
from security import blockchain_client

from shared.config import *

# ===========================
# APP
# ===========================

app = Flask(__name__)


# ===========================
# HELPERS
# ===========================

def derive_block_id(partial_id: str) -> str:
    """
    Deterministic FullBlock ID derived from the PartialBlock ID, so the
    two remain traceable to each other in logs/results without the edge
    gateway having to invent and pass a second identifier.
    """
    if partial_id.startswith("TX-"):
        return "BLK-" + partial_id[3:]
    return "BLK-" + partial_id


def generate_nonce() -> str:
    return secrets.token_hex(16)


# ===========================
# FINALIZE + COMMIT
# ===========================

@app.route("/finalize_block", methods=["POST"])
def finalize_block():
    """
    Called by the edge gateway after SubmitPartialBlock succeeds.

    Body:
        partial_id   : the PartialBlockID already submitted on-chain
        evidence      : the original evidence dict (for independent
                         signature re-verification)
        signature     : hex ML-DSA signature over canonical evidence JSON
        public_key    : hex ML-DSA public key
        evidence_hash : hex SHA-256 commitment (should match the
                         EncryptedTx already stored on-chain for this
                         partial block)

    The cloud server does NOT trust the edge's own verification result.
    It independently recomputes the canonical evidence bytes and
    re-verifies the ML-DSA signature before calling FinalizeFullBlock
    with signature_verified="true"/"false" accordingly. If verification
    fails, the block is finalized as unverified (chaincode will reject
    it — see FinalizeFullBlock's check) rather than silently proceeding.
    """
    data = request.json or {}

    performance = {}

    partial_id = data.get("partial_id")
    evidence = data.get("evidence")
    signature = data.get("signature")
    public_key = data.get("public_key")
    evidence_hash = data.get("evidence_hash")

    missing = [
        name for name, val in
        [("partial_id", partial_id), ("evidence", evidence),
         ("signature", signature), ("public_key", public_key),
         ("evidence_hash", evidence_hash)]
        if not val
    ]
    if missing:
        return jsonify({
            "status": "rejected",
            "reason": f"missing required fields: {', '.join(missing)}"
        }), 400

    print()
    print("==================================================")
    print("CLOUD: INDEPENDENT SIGNATURE RE-VERIFICATION")
    print("==================================================")

    # Recompute canonical evidence bytes exactly as the edge did
    # (security/evidence_security.py: sort_keys=True, no whitespace)
    # and independently re-check both the hash commitment and the
    # ML-DSA signature. The cloud does not trust the edge's own
    # verification result.
    evidence_bytes = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    recomputed_hash = blockchain_client.compute_evidence_hash(evidence)
    hash_matches = recomputed_hash == evidence_hash

    verify_start = time.perf_counter()
    try:
        signature_valid = verify_packet(
            evidence_bytes,
            bytes.fromhex(signature),
            bytes.fromhex(public_key),
        )
    except Exception as e:
        signature_valid = False
        print(f"Signature verification raised: {e}")
    performance["Cloud ML-DSA Re-Verification"] = (
        time.perf_counter() - verify_start
    ) * 1000

    print(f"Hash Commitment Match   : {'YES' if hash_matches else 'NO'}")
    print(f"Signature Valid         : {'YES' if signature_valid else 'NO'}")
    print(f"Re-Verification Time    : "
          f"{performance['Cloud ML-DSA Re-Verification']:.3f} ms")

    signature_verified = "true" if (hash_matches and signature_valid) else "false"

    block_id = derive_block_id(partial_id)
    nonce = generate_nonce()

    print("\n==================================================")
    print("CLOUD: FINALIZE FULL BLOCK")
    print("==================================================")
    print(f"Partial Block ID        : {partial_id}")
    print(f"Full Block ID           : {block_id}")
    print(f"Signature Verified Flag : {signature_verified}")

    try:
        finalize_ms = blockchain_client.finalize_full_block(
            block_id=block_id,
            partial_id=partial_id,
            nonce=nonce,
            signature_verified=signature_verified,
        )
        performance["Blockchain FinalizeFullBlock"] = finalize_ms
        print(f"Status                  : PROPOSED ({finalize_ms:.1f}ms)")
    except Exception as e:
        print(f"Status                  : FINALIZE FAILED ({e})")
        return jsonify({
            "status": "finalize_failed",
            "partial_id": partial_id,
            "block_id": block_id,
            "reason": str(e),
            "hash_matches": hash_matches,
            "signature_valid": signature_valid,
        }), 422

    if signature_verified != "true":
        # Chaincode's FinalizeFullBlock already refuses to finalize an
        # unverified block, so in practice the try block above will have
        # raised before we get here. This branch exists as a defensive
        # backstop in case that check is ever loosened.
        return jsonify({
            "status": "unverified",
            "partial_id": partial_id,
            "block_id": block_id,
            "hash_matches": hash_matches,
            "signature_valid": signature_valid,
        }), 401

    print("\n==================================================")
    print("CLOUD: COMMIT FULL BLOCK (CONSENSUS)")
    print("==================================================")

    try:
        commit_ms = blockchain_client.commit_full_block(block_id)
        performance["Blockchain CommitFullBlock"] = commit_ms
        print(f"Status                  : COMMITTED ({commit_ms:.1f}ms)")
    except Exception as e:
        print(f"Status                  : COMMIT FAILED ({e})")
        return jsonify({
            "status": "commit_failed",
            "partial_id": partial_id,
            "block_id": block_id,
            "reason": str(e),
        }), 422

    total_ms = sum(performance.values())

    print("\n==================================================")
    print("CLOUD: BLOCKCHAIN PERFORMANCE")
    print("==================================================")
    for name, value in performance.items():
        print(f"{name:<32}: {value:.3f} ms")
    print("-----------------------------------------------")
    print(f"{'Total':<32}: {total_ms:.3f} ms")

    return jsonify({
        "status": "committed",
        "partial_id": partial_id,
        "block_id": block_id,
        "hash_matches": hash_matches,
        "signature_valid": signature_valid,
        "performance_ms": performance,
        "total_ms": total_ms,
    })


# ===========================
# VERIFY (AUDIT) ENDPOINT
# ===========================

@app.route("/verify_block/<block_id>", methods=["POST"])
def verify_block(block_id):
    """
    Audit endpoint: given a block_id and the (presumably off-chain-stored)
    evidence dict, recompute its hash and confirm it matches the
    on-chain commitment. Useful for a tamper-evidence experiment in the
    paper's evaluation section.

    Body: { "evidence": {...} }
    """
    data = request.json or {}
    evidence = data.get("evidence")
    if evidence is None:
        return jsonify({"status": "error", "reason": "evidence required"}), 400

    try:
        result = blockchain_client.verify_evidence_integrity(block_id, evidence)
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e)}), 404

    return jsonify(result)


# ===========================
# CHAIN STATUS
# ===========================

@app.route("/chain_meta", methods=["GET"])
def chain_meta():
    try:
        meta = blockchain_client.get_chain_meta()
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e)}), 500
    return jsonify(meta)


# ===========================
# START SERVER
# ===========================

if __name__ == "__main__":

    print()
    print("==============================")
    print(" Cloud Blockchain Server ")
    print("==============================")

    app.run(
        host="0.0.0.0",
        port=CLOUD_PORT,
        debug=False,
    )