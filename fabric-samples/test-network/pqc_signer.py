"""
pqc_signer.py

ML-DSA (Dilithium, FIPS 204) signing utilities for the application-layer
PQC integration with Hyperledger Fabric.

Depends on liboqs-python, which wraps the liboqs C library. Install:
    1. Build/install liboqs (C library) — see https://github.com/open-quantum-safe/liboqs
    2. pip install liboqs-python

If liboqs is unavailable on a teammate's machine (e.g. no C toolchain),
this module falls back to the pure-Python `dilithium-py` package so the
rest of the pipeline (IoT sim -> sign -> submit) still runs end-to-end.
Note: dilithium-py is NOT side-channel hardened; only use the fallback
for functional testing/demos, not for any security-latency benchmarking
claims in your report.
"""

from __future__ import annotations
import os

ALG_NAME = "ML-DSA-65"  # NIST security level 3 — matches chaincode's mldsa65

_BACKEND = None

try:
    from oqs import Signature as OQSSignature
    _BACKEND = "liboqs"
except (ImportError, SystemExit):
    _BACKEND = None

if _BACKEND is None:
    try:
        from dilithium_py.ml_dsa import ML_DSA_65
        _BACKEND = "dilithium-py"
    except ImportError:
        raise RuntimeError(
            "No PQC signature backend available. Install one of:\n"
            "  pip install liboqs-python   (requires liboqs C library built first)\n"
            "  pip install dilithium-py    (pure Python fallback, demo only)"
        )


def backend_name() -> str:
    return _BACKEND


def generate_keypair() -> tuple[bytes, bytes]:
    """Returns (public_key_bytes, private_key_bytes)."""
    if _BACKEND == "liboqs":
        with OQSSignature(ALG_NAME) as signer:
            public_key = signer.generate_keypair()
            private_key = signer.export_secret_key()
        return public_key, private_key
    else:  # dilithium-py
        public_key, private_key = ML_DSA_65.keygen()
        return public_key, private_key


def sign(private_key: bytes, message: bytes, context: bytes = b"") -> bytes:
    """Signs `message` using ML-DSA-65 with an optional FIPS 204 context string.

    The chaincode calls mldsa65.Verify(pub, msgHash, []byte(txID), sig) — i.e.
    it uses the record's txID as the context, NOT concatenated into the message.
    Callers in this codebase MUST pass context=txID.encode() to match, or
    verification will fail on-chain even though the signature is "valid".
    """
    if _BACKEND == "liboqs":
        with OQSSignature(ALG_NAME, secret_key=private_key) as signer:
            return signer.sign_with_ctx_str(message, context)
    else:
        if context:
            raise NotImplementedError(
                "dilithium-py fallback does not support FIPS 204 context strings. "
                "Signatures produced here will NOT verify against chaincode that "
                "checks a non-empty context (e.g. txID). Install liboqs-python for "
                "any test that needs to actually pass chaincode verification."
            )
        return ML_DSA_65.sign(private_key, message)


def verify(public_key: bytes, message: bytes, signature: bytes, context: bytes = b"") -> bool:
    """Local verification — useful for client-side sanity checks before
    submitting to Fabric; the chaincode does the authoritative verification.
    Must be called with the same context used at sign time."""
    if _BACKEND == "liboqs":
        with OQSSignature(ALG_NAME) as verifier:
            return verifier.verify_with_ctx_str(message, signature, context, public_key)
    else:
        if context:
            raise NotImplementedError(
                "dilithium-py fallback does not support FIPS 204 context strings."
            )
        return ML_DSA_65.verify(public_key, message, signature)


if __name__ == "__main__":
    import hashlib
    import time

    print(f"Using backend: {backend_name()}")

    pub, priv = generate_keypair()
    print(f"Public key size:  {len(pub)} bytes")
    print(f"Private key size: {len(priv)} bytes")

    tx_id = "asset001"
    payload = b'{"deviceId":"sensor01","temp":22.5,"ts":1751500000}'
    digest = hashlib.sha256(payload).digest()
    ctx = tx_id.encode()  # matches chaincode's use of txID as context

    t0 = time.perf_counter()
    sig = sign(priv, digest, context=ctx)
    t1 = time.perf_counter()
    print(f"Signature size:   {len(sig)} bytes")
    print(f"Sign time:        {(t1 - t0) * 1000:.3f} ms")

    t0 = time.perf_counter()
    ok = verify(pub, digest, sig, context=ctx)
    t1 = time.perf_counter()
    print(f"Verify result:    {ok}")
    print(f"Verify time:      {(t1 - t0) * 1000:.3f} ms")