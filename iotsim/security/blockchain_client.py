import hashlib
import json
import os
import subprocess
import time

TEST_NETWORK_DIR = os.path.expanduser(
    "~/testingmultpeers/fabric-samples/test-network"
)
ORG_BASE = os.path.join(TEST_NETWORK_DIR, "organizations")

CHANNEL = "mychannel"
CC_NAME = "iotcc"

ORDERER_ADDR = "localhost:7050"
ORDERER_TLS_HOSTNAME = "orderer.example.com"
ORDERER_CA = os.path.join(
    ORG_BASE,
    "ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem",
)

# (address, tls root cert) — matches the proven-working benchmark script:
# 2 peers (org1, org2), using each peer's own tls/ca.crt rather than the
# org-level msp/tlscacerts cert. The 5-peer / msp-tlscacerts combination
# was producing "creator org unknown, creator is malformed" endorsement
# failures on invoke (write) calls specifically; queries were unaffected
# since they don't go through the orderer/endorsement path.
PEERS = [
    ("localhost:7051", os.path.join(
        ORG_BASE, "peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt")),
    ("localhost:9051", os.path.join(
        ORG_BASE, "peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt")),
]

# Fabric CLI config + identity. Equivalent to what `source envVar.sh && setGlobals 1`
# does manually in a terminal — baked in here so any caller (edge gateway, cloud
# server, a raw REPL) works without needing to export these first.
FABRIC_BIN_DIR = os.path.expanduser("~/testingmultpeers/fabric-samples/bin")
FABRIC_CFG_PATH = os.path.expanduser("~/testingmultpeers/fabric-samples/config/")

# Submitting identity: Org1 admin (matches setGlobals 1)
CORE_PEER_LOCALMSPID = "Org1MSP"
CORE_PEER_TLS_ROOTCERT_FILE = os.path.join(
    ORG_BASE,
    "peerOrganizations/org1.example.com/tlsca/tlsca.org1.example.com-cert.pem",
)
CORE_PEER_MSPCONFIGPATH = os.path.join(
    ORG_BASE,
    "peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp",
)
CORE_PEER_ADDRESS = "localhost:7051"



def _fabric_env():
    env = os.environ.copy()
    env["FABRIC_CFG_PATH"] = FABRIC_CFG_PATH
    env["PATH"] = FABRIC_BIN_DIR + os.pathsep + env.get("PATH", "")

    env["CORE_PEER_TLS_ENABLED"] = "true"
    env["CORE_PEER_LOCALMSPID"] = CORE_PEER_LOCALMSPID
    env["CORE_PEER_TLS_ROOTCERT_FILE"] = CORE_PEER_TLS_ROOTCERT_FILE
    env["CORE_PEER_MSPCONFIGPATH"] = CORE_PEER_MSPCONFIGPATH
    env["CORE_PEER_ADDRESS"] = CORE_PEER_ADDRESS
    return env


def _invoke(function, args):
    cmd = [
        "peer", "chaincode", "invoke",
        "-o", ORDERER_ADDR,
        "--ordererTLSHostnameOverride", ORDERER_TLS_HOSTNAME,
        "--tls", "--cafile", ORDERER_CA,
        "-C", CHANNEL, "-n", CC_NAME,
        "--waitForEvent",
    ]
    for addr, ca in PEERS:
        cmd += ["--peerAddresses", addr, "--tlsRootCertFiles", ca]
    cmd += ["-c", json.dumps({"function": function, "Args": args})]

    start = time.perf_counter()
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30, env=_fabric_env()
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    if result.returncode != 0:
        raise RuntimeError(f"{function} failed: {result.stderr.strip()}")

    return elapsed_ms


def _query(function, args):
    """
    Read-only path for GetXxx chaincode functions. No orderer, no
    multi-peer endorsement, no --waitForEvent — a single peer answers
    directly from its ledger. Returns the parsed JSON response.
    """
    cmd = [
        "peer", "chaincode", "query",
        "-C", CHANNEL, "-n", CC_NAME,
        "-c", json.dumps({"function": function, "Args": args}),
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30, env=_fabric_env()
    )

    if result.returncode != 0:
        raise RuntimeError(f"{function} failed: {result.stderr.strip()}")

    stdout = result.stdout.strip()
    if not stdout:
        return None
    return json.loads(stdout)


def register_device(device_id, device_type, edge_cluster, org_msp):
    return _invoke("RegisterDevice", [device_id, device_type, edge_cluster, org_msp])


def submit_record(tx_id, device_id, edge_cluster, data_hash, status):
    return _invoke("SubmitRecord", [tx_id, device_id, edge_cluster, data_hash, status])


def raise_alert(alert_id, tx_id, device_id, severity, description, flagged_by):
    return _invoke("RaiseAlert", [alert_id, tx_id, device_id, severity, description, flagged_by])

def submit_partial_block(
    partial_id,
    owner,
    owner_pub_key,
    encrypted_tx,
    signature,
    edge_cluster,
    device_id,
):
    return _invoke(
        "SubmitPartialBlock",
        [
            partial_id,
            owner,
            owner_pub_key,
            encrypted_tx,
            signature,
            edge_cluster,
            device_id,
        ],
    )

def finalize_full_block(
    block_id,
    partial_id,
    nonce,
    signature_verified,
):
    return _invoke(
        "FinalizeFullBlock",
        [
            block_id,
            partial_id,
            nonce,
            signature_verified,
        ],
    )


def finalize_batch_full_block(block_id, partial_ids, nonce, signatures_verified):
    """
    Folds multiple PENDING partial blocks (partial_ids: list[str]) into a
    single FullBlock via a Merkle root over their commitments. Caller is
    responsible for having independently verified every member's signature
    before calling this with signatures_verified="true" -- the chaincode
    does not re-verify signatures itself for batches, it only records the
    caller's attestation (same trust model as the single-block flow's
    signature_verified flag).
    """
    return _invoke(
        "FinalizeBatchFullBlock",
        [
            block_id,
            json.dumps(partial_ids),
            nonce,
            signatures_verified,
        ],
    )


def commit_full_block(block_id):
    """
    Advances the chain tip: sets PreviousHash from ChainMeta, recomputes
    Hash, marks ConsensusStatus COMMITTED. Must be called after
    FinalizeFullBlock (which leaves the block PROPOSED) for the block to
    actually join the chain.
    """
    return _invoke("CommitFullBlock", [block_id])


def reject_full_block(block_id):
    """
    Marks a PROPOSED full block REJECTED. Fails if the block is already
    COMMITTED.
    """
    return _invoke("RejectFullBlock", [block_id])


def get_partial_block(partial_id):
    return _query("GetPartialBlock", [partial_id])


def get_full_block(block_id):
    return _query("GetFullBlock", [block_id])


def get_chain_meta():
    return _query("GetChainMeta", [])


def get_all_full_blocks():
    return _query("GetAllFullBlocks", [])


# ---------- Evidence integrity verification ----------
#
# EncryptedTx on-chain is not an encrypted payload — it's a SHA-256
# commitment (digest) of the full evidence record, which is retained
# off-chain (e.g. edge storage, a DB, wherever the caller persists the
# `evidence` dict). This function lets an auditor/verifier re-derive that
# commitment from a stored evidence object and confirm it matches what
# was anchored on-chain for a given full block, i.e. that the off-chain
# evidence has not been tampered with since it was committed.

def compute_evidence_hash(evidence):
    """
    Recompute the SHA-256 commitment for an evidence object the same way
    the edge gateway does before submission: canonical JSON (sorted keys,
    no incidental whitespace differences) -> UTF-8 bytes -> SHA-256 hex.

    `evidence` may be a dict/list (will be json.dumps'd) or an already-
    serialized string (used as-is).
    """
    if isinstance(evidence, (dict, list)):
        payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    else:
        payload = evidence
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_evidence_integrity(block_id, evidence):
    """
    Fetches the committed FullBlock for `block_id` and checks whether
    SHA-256(evidence) matches its EncryptedTx field (the on-chain
    commitment). Returns a dict summarizing the result rather than a bare
    bool, so callers/experiments can log full detail:

        {
            "block_id": ...,
            "consensus_status": "COMMITTED" | "PROPOSED" | "REJECTED",
            "onchain_commitment": <hex digest stored on-chain>,
            "recomputed_commitment": <hex digest recomputed locally>,
            "verified": True | False,
        }

    Raises RuntimeError if the block does not exist (propagated from
    _query / GetFullBlock).
    """
    full_block = get_full_block(block_id)
    onchain_commitment = full_block.get("encryptedTx", "")
    recomputed_commitment = compute_evidence_hash(evidence)

    return {
        "block_id": block_id,
        "consensus_status": full_block.get("consensusStatus"),
        "onchain_commitment": onchain_commitment,
        "recomputed_commitment": recomputed_commitment,
        "verified": onchain_commitment == recomputed_commitment,
    }