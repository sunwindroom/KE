import base64
import hashlib

import bcrypt
from cryptography.fernet import Fernet, InvalidToken


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


_fernet_cache: dict[str, Fernet] = {}


def _get_fernet(secret: str) -> Fernet:
    """基于 JWT_SECRET_KEY（或专用 CONFIG_ENCRYPTION_KEY）派生一把稳定的 Fernet 对称密钥，
    用于加密数据库中保存的敏感配置项（如 LLM API Key、各类中间件密码）。

    不引入额外的必填环境变量：只要 JWT_SECRET_KEY 不变，派生出的密钥就不变，
    重启后依然可以解密数据库里已保存的密文；如果 JWT_SECRET_KEY 更换，
    旧密文将无法解密，需要在设置页重新填写一次相关密钥（这是预期行为，不是 Bug）。
    """
    if secret in _fernet_cache:
        return _fernet_cache[secret]
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    fernet = Fernet(key)
    _fernet_cache[secret] = fernet
    return fernet


def encrypt_secret(plain_value: str, master_key: str) -> str:
    if plain_value is None:
        return ""
    return _get_fernet(master_key).encrypt(plain_value.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_value: str, master_key: str) -> str:
    if not cipher_value:
        return ""
    try:
        return _get_fernet(master_key).decrypt(cipher_value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        # 解密失败（通常是主密钥已更换）：不让接口 500，返回空串，由调用方按“未配置”处理。
        return ""


def mask_secret(value: str) -> str:
    """只暴露末 4 位，其余打码；未配置时返回空字符串。"""
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]
