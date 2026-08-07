import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def _derive_fernet_key(secret_key: str) -> bytes:
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    settings = get_settings()
    return Fernet(_derive_fernet_key(settings.secret_key))


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt stored secret; SECRET_KEY may have changed") from exc


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency. No-op when no api_key is configured (local/dev use).

    Treats an empty string the same as None: an explicit `API_KEY=` (no value)
    in a .env file is parsed by pydantic-settings as "", not None, and should
    still mean "disabled" rather than "require an empty header value".
    """
    settings = get_settings()
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
