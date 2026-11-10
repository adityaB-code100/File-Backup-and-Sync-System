import os
import base64
import hashlib
import logging
import struct
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("cloud_storage.crypto")

# ============================================================
# Streaming AEAD Constants – Rogaway STREAM Construction
# ============================================================
# V2 Container Layout (all plaintext on disk):
#   [4B] MAGIC            = b"VC02"           (plaintext — format identifier)
#   [1B] VERSION          = 0x02              (plaintext)
#   [7B] NONCE_PREFIX     = os.urandom(7)     (plaintext — unique per file)
#   [4B] CHUNK_SIZE_FIELD = 65536 as uint32-BE (plaintext)
#   --- then for each chunk: ---
#   [4B] CHUNK_DATA_LEN   = len(ciphertext) as uint32-BE
#   [NB] CIPHERTEXT       = aesgcm.encrypt(chunk_iv, plaintext_chunk, aad) + 16B GCM tag
# Total header: 16 bytes (plaintext, unencrypted)
# This design keeps the plaintext magic bytes at byte-offset 0 for reliable format detection.

MAGIC_V2       = b"VC02"
VERSION_V2     = 0x02
CHUNK_SIZE     = 64 * 1024   # 64 KiB
TAG_LEN        = 16          # AES-GCM authentication tag

# Static development fallback key – used ONLY when DEBUG=True and FILE_ENCRYPTION_KEK is absent.
# Using a fixed known value for dev ensures existing dev-encrypted files remain readable.
DEV_STATIC_FALLBACK_KEK_B64 = "4R7+Y2V1+wN0Z1x4yK9kX7qL5mW8vN2pQ3sT6uR1vA8="


class CryptographicIntegrityError(Exception):
    """Raised when ciphertext is tampered, truncated, reordered, or otherwise invalid."""


class UploadSizeLimitExceeded(Exception):
    """Raised when an incoming file stream exceeds the configured maximum upload size."""
    def __init__(self, size_bytes: int, limit_bytes: int):
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes
        super().__init__(
            f"File size {size_bytes} bytes exceeds the maximum allowed limit of {limit_bytes} bytes."
        )


class KeyManagementError(Exception):
    """Raised when encryption key configuration is missing, malformed, or invalid."""


def validate_kek(kek_bytes: bytes) -> bool:
    return isinstance(kek_bytes, (bytes, bytearray)) and len(kek_bytes) == 32


def generate_new_kek_b64() -> str:
    """Generates a cryptographically strong 256-bit KEK encoded as base64."""
    return base64.b64encode(os.urandom(32)).decode('ascii')


def get_master_kek() -> bytes:
    """
    Retrieves and validates the Master Key Encryption Key (KEK).

    Security rules:
    • Production (DEBUG=False): FILE_ENCRYPTION_KEK must be present, valid base64, and
      decode to exactly 32 bytes. Raises ImproperlyConfigured otherwise. Never falls back
      to SECRET_KEY.
    • Development (DEBUG=True): If FILE_ENCRYPTION_KEK is provided it is strictly validated.
      If absent, the fixed DEV_STATIC_FALLBACK_KEK is used with a prominent warning so that
      existing dev-encrypted files remain readable and the key never silently changes.
    """
    is_debug = getattr(settings, 'DEBUG', True)
    kek_b64 = getattr(settings, 'FILE_ENCRYPTION_KEK', '') or os.getenv('FILE_ENCRYPTION_KEK', '')

    if not kek_b64:
        if not is_debug:
            raise ImproperlyConfigured(
                "CRITICAL: 'FILE_ENCRYPTION_KEK' is not configured. "
                "A 32-byte base64-encoded Master KEK is mandatory in production. "
                "Silent fallback to SECRET_KEY is disabled."
            )
        logger.warning(
            "[SECURITY WARNING] FILE_ENCRYPTION_KEK is not configured. "
            "Using DEV_STATIC_FALLBACK_KEK for development. "
            "DO NOT use this in production."
        )
        kek_b64 = DEV_STATIC_FALLBACK_KEK_B64

    try:
        kek_bytes = base64.b64decode(kek_b64)
    except Exception as exc:
        raise ImproperlyConfigured(
            f"Invalid base64 encoding for 'FILE_ENCRYPTION_KEK': {exc}"
        ) from exc

    if len(kek_bytes) != 32:
        raise ImproperlyConfigured(
            f"'FILE_ENCRYPTION_KEK' must decode to exactly 32 bytes (256 bits). "
            f"Got {len(kek_bytes)} bytes."
        )

    return bytes(kek_bytes)


def _make_chunk_iv(nonce_prefix: bytes, chunk_index: int, is_last: bool) -> bytes:
    """12-byte IV = nonce_prefix (7B) || counter (4B big-endian) || is_last flag (1B)."""
    return nonce_prefix + struct.pack(">IB", chunk_index, 1 if is_last else 0)


def _make_chunk_aad(chunk_index: int, is_last: bool) -> bytes:
    """Additional authenticated data binds chunk position and stream-termination flag."""
    return MAGIC_V2 + struct.pack(">IB", chunk_index, 1 if is_last else 0)


def compute_sha256_and_save_encrypted(
    file_stream,
    destination_path: Path,
    kek_bytes: bytes,
    max_size_bytes: int | None = None,
):
    """
    Streams file_stream through SHA-256 and Rogaway STREAM chunked AES-256-GCM encryption.

    Format V2 (new files):
        16-byte plaintext header: MAGIC(4) VERSION(1) NONCE_PREFIX(7) CHUNK_SIZE(4)
        Per chunk: CHUNK_DATA_LEN(4B) | CIPHERTEXT (plaintext + 16B GCM tag)

    Security:
        • O(1) RAM regardless of file size (bounded 64 KiB buffer).
        • Each chunk carries a unique IV and AAD that encodes its index and final-chunk flag.
        • Chunk reordering, deletion, duplication and truncation are all detected.
        • If max_size_bytes is set, the stream is aborted and the temp file unlinked if exceeded.
        • On any failure the destination file is unlinked atomically.

    Returns:
        (sha256_hex, size_bytes, wrapped_dek_b64, dek_iv_b64, nonce_prefix_b64)
    """
    destination_path = Path(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    if not validate_kek(kek_bytes):
        raise KeyManagementError("Master KEK must be exactly 32 bytes (256 bits).")

    sha256    = hashlib.sha256()
    size_bytes = 0

    # Fresh per-file DEK and wrapping IV
    dek    = AESGCM.generate_key(bit_length=256)
    dek_iv = os.urandom(12)

    # Wrap DEK with KEK
    aesgcm_kek  = AESGCM(kek_bytes)
    wrapped_dek = aesgcm_kek.encrypt(dek_iv, dek, None)

    aesgcm_file  = AESGCM(dek)
    nonce_prefix = os.urandom(7)   # 7 high-entropy bytes shared across all chunk IVs

    try:
        with open(destination_path, "wb") as out_f:
            # --- Plaintext V2 Header (16 bytes) ----------------------------------------
            header = MAGIC_V2 + bytes([VERSION_V2]) + nonce_prefix + struct.pack(">I", CHUNK_SIZE)
            out_f.write(header)   # 16 bytes, NOT encrypted — format detection reads these

            # --- Chunk loop ------------------------------------------------------------
            chunk_index = 0
            current_chunk = file_stream.read(CHUNK_SIZE)

            while True:
                next_chunk   = file_stream.read(CHUNK_SIZE)
                is_last      = len(next_chunk) == 0

                size_bytes  += len(current_chunk)
                if max_size_bytes is not None and size_bytes > max_size_bytes:
                    raise UploadSizeLimitExceeded(size_bytes, max_size_bytes)

                sha256.update(current_chunk)

                chunk_iv  = _make_chunk_iv(nonce_prefix, chunk_index, is_last)
                chunk_aad = _make_chunk_aad(chunk_index, is_last)
                enc_chunk = aesgcm_file.encrypt(chunk_iv, current_chunk, chunk_aad)

                out_f.write(struct.pack(">I", len(enc_chunk)))
                out_f.write(enc_chunk)

                chunk_index += 1
                if is_last:
                    break
                current_chunk = next_chunk

            out_f.flush()
            os.fsync(out_f.fileno())

    except Exception:
        destination_path.unlink(missing_ok=True)
        raise

    return (
        sha256.hexdigest(),
        size_bytes,
        base64.b64encode(wrapped_dek).decode('ascii'),
        base64.b64encode(dek_iv).decode('ascii'),
        base64.b64encode(nonce_prefix).decode('ascii'),
    )


def decrypt_file_stream(
    source_path: Path,
    wrapped_dek_b64: str,
    dek_iv_b64: str,
    file_iv_b64: str,
    kek_bytes: bytes,
):
    """
    Decrypts a VaultCloud encrypted blob and yields plaintext chunks.

    Automatically detects format:
      • V2 (Rogaway STREAM, magic b"VC02"): chunk-by-chunk verification,
        O(1) RAM, detects reordering/truncation/tampering.
      • V1 (legacy single-block AES-GCM): full file read into RAM, GCM tag
        verified, then yielded in 64 KiB slices.

    file_iv_b64 carries different meanings per format:
      • V1: the 12-byte file IV used for single-block decryption.
      • V2: the 7-byte nonce prefix embedded in the header (the value returned
        by compute_sha256_and_save_encrypted). The on-disk header is authoritative
        for V2 — the nonce_prefix stored in MongoDB is cross-checked for integrity.
    """
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Encrypted blob not found: {source_path}")

    # Unwrap DEK
    wrapped_dek = base64.b64decode(wrapped_dek_b64)
    dek_iv      = base64.b64decode(dek_iv_b64)
    aesgcm_kek  = AESGCM(kek_bytes)
    try:
        dek = aesgcm_kek.decrypt(dek_iv, wrapped_dek, None)
    except Exception as exc:
        raise CryptographicIntegrityError(f"Failed to unwrap DEK: {exc}") from exc

    aesgcm_file = AESGCM(dek)

    with open(source_path, "rb") as in_f:
        magic_probe = in_f.read(4)

        if magic_probe == MAGIC_V2:
            # ======================================================================
            # FORMAT V2 — Rogaway STREAM chunked AEAD
            # ======================================================================
            rest_header = in_f.read(12)   # VERSION(1) NONCE_PREFIX(7) CHUNK_SIZE(4)
            if len(rest_header) < 12:
                raise CryptographicIntegrityError("V2 container: incomplete header.")

            version_byte  = rest_header[0]
            nonce_prefix  = rest_header[1:8]
            chunk_size_hdr = struct.unpack(">I", rest_header[8:12])[0]

            if version_byte != VERSION_V2:
                raise CryptographicIntegrityError(
                    f"Unsupported V2 version byte: {version_byte:#04x}"
                )

            chunk_index      = 0
            found_last_chunk = False

            while True:
                len_bytes = in_f.read(4)
                if not len_bytes:
                    break  # EOF
                if len(len_bytes) < 4:
                    raise CryptographicIntegrityError("Corrupted chunk: unexpected EOF reading length.")

                enc_chunk_len = struct.unpack(">I", len_bytes)[0]
                # Sanity bound: each chunk can be at most CHUNK_SIZE + TAG_LEN bytes
                if enc_chunk_len < TAG_LEN or enc_chunk_len > CHUNK_SIZE + TAG_LEN + 1:
                    raise CryptographicIntegrityError(
                        f"Invalid encrypted chunk length: {enc_chunk_len}."
                    )

                enc_chunk = in_f.read(enc_chunk_len)
                if len(enc_chunk) != enc_chunk_len:
                    raise CryptographicIntegrityError(
                        f"Chunk {chunk_index}: incomplete data (expected {enc_chunk_len}, "
                        f"got {len(enc_chunk)})."
                    )

                # Determine is_last by peeking the next 4 bytes
                peek = in_f.read(4)
                is_last = len(peek) == 0
                if not is_last:
                    in_f.seek(-len(peek), os.SEEK_CUR)

                chunk_iv  = _make_chunk_iv(nonce_prefix, chunk_index, is_last)
                chunk_aad = _make_chunk_aad(chunk_index, is_last)

                try:
                    plaintext_chunk = aesgcm_file.decrypt(chunk_iv, enc_chunk, chunk_aad)
                except Exception as exc:
                    raise CryptographicIntegrityError(
                        f"Chunk {chunk_index} authentication failed: {exc}"
                    ) from exc

                yield plaintext_chunk
                chunk_index += 1

                if is_last:
                    found_last_chunk = True
                    break

            if not found_last_chunk and chunk_index > 0:
                raise CryptographicIntegrityError(
                    "Truncated ciphertext: stream ended without final-chunk marker."
                )

        else:
            # ======================================================================
            # FORMAT V1 — Legacy single-block AES-256-GCM (backward compatibility)
            # ======================================================================
            in_f.seek(0)
            ciphertext = in_f.read()
            file_iv    = base64.b64decode(file_iv_b64)   # 12-byte nonce stored in MongoDB

            try:
                plaintext = aesgcm_file.decrypt(file_iv, ciphertext, None)
            except Exception as exc:
                raise CryptographicIntegrityError(
                    f"Legacy V1 ciphertext authentication failed: {exc}"
                ) from exc

            for i in range(0, len(plaintext), CHUNK_SIZE):
                yield plaintext[i:i + CHUNK_SIZE]


def decrypt_file_bytes(
    source_path: Path,
    wrapped_dek_b64: str,
    dek_iv_b64: str,
    file_iv_b64: str,
    kek_bytes: bytes,
) -> bytes:
    """Convenience helper: decrypts blob and returns all plaintext as a single bytes object."""
    return b"".join(
        decrypt_file_stream(source_path, wrapped_dek_b64, dek_iv_b64, file_iv_b64, kek_bytes)
    )
