import os
import sys
import json
import time
import secrets
import threading
import uuid

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
# BATCH QUEUE
# ===========================
#
# Instead of committing every finalized attack as its own FullBlock
# (~2s/block observed earlier), pending, independently-verified partial
# blocks are accumulated here and flushed together into ONE FullBlock via
# FinalizeBatchFullBlock, amortizing the finalize+commit cost across many
# attacks. A block is flushed when it hits BATCH_MAX_SIZE members or
# BATCH_MAX_WAIT_SECONDS have elapsed since the oldest queued member,
# whichever comes first -- so a lone attack during quiet periods still
# gets committed promptly rather than waiting indefinitely for company.

BATCH_MAX_SIZE = 10
BATCH_MAX_WAIT_SECONDS = 15

batch_lock = threading.Lock()
batch_queue = []  # list of dicts: {partial_id, queued_at}


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
# BATCH FINALIZE
# ===========================

@app.route("/finalize_block_batched", methods=["POST"])
def finalize_block_batched():
    """
    Same independent re-verification as /finalize_block, but on success
    the partial block is queued rather than immediately finalized+committed
    individually. It will be folded into a Merkle-batch FullBlock the next
    time the queue flushes (see flush_batch()). Returns immediately with
    status "queued" -- the caller does not wait for the eventual on-chain
    commit. Poll /batch_status or check /alerts / GetFullBlock later for
    the resulting batch block_id.
    """
    data = request.json or {}

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

    evidence_bytes = json.dumps(
        evidence, sort_keys=True, separators=(",", ":"),
    ).encode()

    recomputed_hash = blockchain_client.compute_evidence_hash(evidence)
    hash_matches = recomputed_hash == evidence_hash

    try:
        signature_valid = verify_packet(
            evidence_bytes,
            bytes.fromhex(signature),
            bytes.fromhex(public_key),
        )
    except Exception as e:
        signature_valid = False
        print(f"Signature verification raised: {e}")

    if not (hash_matches and signature_valid):
        return jsonify({
            "status": "rejected",
            "partial_id": partial_id,
            "hash_matches": hash_matches,
            "signature_valid": signature_valid,
            "reason": "hash commitment or signature verification failed; not queued",
        }), 401

    with batch_lock:
        batch_queue.append({
            "partial_id": partial_id,
            "queued_at": time.time(),
        })
        queue_size = len(batch_queue)

    print(f"\n[BATCH] Queued {partial_id} ({queue_size} pending)")

    flushed_block_id = None
    if queue_size >= BATCH_MAX_SIZE:
        flushed_block_id = flush_batch()

    return jsonify({
        "status": "queued",
        "partial_id": partial_id,
        "queue_size": queue_size,
        "flushed_block_id": flushed_block_id,
    })


def flush_batch():
    """
    Drains the current batch queue and commits everything in it as one
    Merkle-batch FullBlock. Returns the new block_id, or None if the queue
    was empty. Safe to call concurrently -- the queue swap happens under
    batch_lock, so only one flush proceeds even if the size-trigger and
    the timer-thread race.
    """
    with batch_lock:
        if not batch_queue:
            return None
        members = batch_queue[:]
        batch_queue.clear()

    partial_ids = [m["partial_id"] for m in members]
    block_id = "BATCH-" + uuid.uuid4().hex[:16]
    nonce = secrets.token_hex(16)

    print("\n==================================================")
    print(f"CLOUD: FLUSHING BATCH ({len(partial_ids)} members)")
    print("==================================================")
    print(f"Batch Block ID : {block_id}")
    for pid in partial_ids:
        print(f"  - {pid}")

    try:
        finalize_ms = blockchain_client.finalize_batch_full_block(
            block_id=block_id,
            partial_ids=partial_ids,
            nonce=nonce,
            signatures_verified="true",
        )
        print(f"Batch Finalized : PROPOSED ({finalize_ms:.1f}ms)")
    except Exception as e:
        print(f"Batch Finalize FAILED: {e}")
        # Members already passed independent verification when queued;
        # put them back so they aren't silently dropped, and surface the
        # failure for investigation rather than losing evidence.
        with batch_lock:
            batch_queue.extend(members)
        return None

    try:
        commit_ms = blockchain_client.commit_full_block(block_id)
        print(f"Batch Committed : COMMITTED ({commit_ms:.1f}ms)")
    except Exception as e:
        print(f"Batch Commit FAILED: {e}")
        return block_id  # finalized but not committed; caller can inspect/retry commit

    return block_id


@app.route("/batch_status", methods=["GET"])
def batch_status():
    with batch_lock:
        pending = [m["partial_id"] for m in batch_queue]
        oldest_age = (
            time.time() - min(m["queued_at"] for m in batch_queue)
            if batch_queue else None
        )
    return jsonify({
        "pending_count": len(pending),
        "pending_partial_ids": pending,
        "oldest_pending_age_seconds": oldest_age,
        "batch_max_size": BATCH_MAX_SIZE,
        "batch_max_wait_seconds": BATCH_MAX_WAIT_SECONDS,
    })


@app.route("/flush_batch_now", methods=["POST"])
def flush_batch_now():
    """Manual trigger, mainly for testing without waiting on the timer."""
    block_id = flush_batch()
    return jsonify({"flushed_block_id": block_id})


def _batch_flush_timer():
    """
    Background thread: every second, checks whether the oldest queued
    member has been waiting longer than BATCH_MAX_WAIT_SECONDS, and if so
    flushes the whole queue -- ensuring attacks during quiet periods still
    get committed promptly instead of waiting indefinitely for the queue
    to fill up to BATCH_MAX_SIZE.
    """
    while True:
        time.sleep(1)
        with batch_lock:
            if not batch_queue:
                continue
            oldest_age = time.time() - min(m["queued_at"] for m in batch_queue)
        if oldest_age >= BATCH_MAX_WAIT_SECONDS:
            flush_batch()


threading.Thread(target=_batch_flush_timer, daemon=True).start()


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