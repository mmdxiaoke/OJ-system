"""安全相关工具：密码哈希、会话 ID、敏感配置加密。"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import os
import secrets
import uuid

from backend import config
from backend.core import storage

# ---------------------------------------------------------------------------
# 密码哈希（bcrypt）
# ---------------------------------------------------------------------------
try:  # pragma: no cover - 环境差异
    import bcrypt

    _HAS_BCRYPT = True
except ImportError:  # pragma: no cover
    _HAS_BCRYPT = False


def hash_password(password: str) -> str:
    """bcrypt 哈希（bcrypt 只取前 72 字节，这里显式截断避免抛错）。"""
    raw = password.encode("utf-8")[:72]
    if _HAS_BCRYPT:
        return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")
    # 退化方案：PBKDF2-HMAC-SHA256，仅在 bcrypt 不可用时使用
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw, salt.encode(), 200_000)
    return f"pbkdf2${salt}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    raw = password.encode("utf-8")[:72]
    if stored.startswith("pbkdf2$"):
        _, salt, digest = stored.split("$", 2)
        calc = hashlib.pbkdf2_hmac("sha256", raw, salt.encode(), 200_000)
        return hmac.compare_digest(base64.b64encode(calc).decode(), digest)
    if not _HAS_BCRYPT:
        return False
    try:
        return bcrypt.checkpw(raw, stored.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------
def new_session_id() -> str:
    """使用 uuid4 + 随机字节，保证不可猜测。"""
    return uuid.uuid4().hex + secrets.token_hex(8)


def new_submission_id(n: int) -> str:
    return str(n)


# ---------------------------------------------------------------------------
# 敏感配置加密（模型密钥）
# ---------------------------------------------------------------------------
def _load_master_key() -> bytes:
    if config.SECRET_FILE.exists():
        data = config.SECRET_FILE.read_bytes()
        if len(data) >= 32:
            return data[:32]
    key = secrets.token_bytes(32)
    config.SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SECRET_FILE.write_bytes(key)
    with contextlib.suppress(OSError):  # pragma: no cover - Windows 上可能不支持
        os.chmod(config.SECRET_FILE, 0o600)
    return key


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def encrypt_secret(plaintext: str) -> str:
    """使用 HMAC-SHA256 派生密钥流做流加密，密钥保存在本地且不进入 git。"""
    if plaintext is None:
        return ""
    key = _load_master_key()
    nonce = secrets.token_bytes(16)
    data = plaintext.encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(data, _keystream(key, nonce, len(data)), strict=False))
    tag = hmac.new(key, nonce + data, hashlib.sha256).digest()[:16]
    return base64.b64encode(nonce + tag + cipher).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        blob = base64.b64decode(token.encode("ascii"))
        nonce, tag, cipher = blob[:16], blob[16:32], blob[32:]
        key = _load_master_key()
        data = bytes(a ^ b for a, b in zip(cipher, _keystream(key, nonce, len(cipher)), strict=False))
        if not hmac.compare_digest(hmac.new(key, nonce + data, hashlib.sha256).digest()[:16], tag):
            return ""
        return data.decode("utf-8")
    except Exception:
        return ""


def mask_secret(token: str) -> str:
    return "***" if token else ""


def ensure_storage() -> None:
    storage.ensure_dirs()
