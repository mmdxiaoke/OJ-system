"""AI 模型配置的保存与读取（R2）。

* 提供商 URL / 模型名称 / 模型密钥均由用户在界面配置，不写死在代码里；
* 模型密钥加密后落盘，任何查询接口都不会返回明文。
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

from backend.core import storage
from backend.core.responses import ApiError
from backend.core.security import decrypt_secret, encrypt_secret

DEFAULT_PRICE_UNIT = 1_000_000


def _validate_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ApiError(400, "provider_url is required")
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError(400, "provider_url must be a valid http(s) URL")
    if len(url) > 512:
        raise ApiError(400, "provider_url is too long")
    return url.rstrip("/")


def _positive_float(value, name: str, default: float) -> float:
    if value is None:
        return default
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"{name} must be a number") from None
    if value < 0:
        raise ApiError(400, f"{name} must not be negative")
    return value


async def save_config(payload: dict) -> dict:
    provider_url = _validate_url(payload.get("provider_url"))
    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ApiError(400, "model is required")
    api_key = payload.get("api_key")

    current = await get_raw_config()
    if api_key is None or api_key == "":
        # 未提供新密钥时沿用旧密钥（便于只改模型名）
        api_key_enc = (current or {}).get("api_key_enc", "")
        if not api_key_enc:
            raise ApiError(400, "api_key is required")
    else:
        if not isinstance(api_key, str) or len(api_key) > 512:
            raise ApiError(400, "api_key must be a string")
        api_key_enc = encrypt_secret(api_key.strip())

    price_unit = payload.get("price_unit")
    if price_unit is None:
        price_unit = (current or {}).get("price_unit", DEFAULT_PRICE_UNIT)
    try:
        price_unit = int(price_unit)
    except (TypeError, ValueError):
        raise ApiError(400, "price_unit must be an integer") from None
    if price_unit <= 0:
        raise ApiError(400, "price_unit must be positive")

    config = {
        "provider_url": provider_url,
        "model": model.strip(),
        "api_key_enc": api_key_enc,
        "input_price": _positive_float(payload.get("input_price"), "input_price",
                                       float((current or {}).get("input_price", 0.0))),
        "output_price": _positive_float(payload.get("output_price"), "output_price",
                                        float((current or {}).get("output_price", 0.0))),
        "price_unit": price_unit,
        "updated_at": time.time(),
    }
    await storage.ai_config_store.write({"config": config})
    return public_view(config)


async def get_raw_config() -> dict | None:
    data = await storage.ai_config_store.read()
    return data.get("config")


def public_view(config: dict | None) -> dict:
    """对外的配置视图：绝不包含密钥明文。"""
    if not config:
        return {
            "provider_url": "",
            "model": "",
            "api_key_configured": False,
            "input_price": 0.0,
            "output_price": 0.0,
            "price_unit": DEFAULT_PRICE_UNIT,
        }
    return {
        "provider_url": config.get("provider_url", ""),
        "model": config.get("model", ""),
        "api_key_configured": bool(config.get("api_key_enc")),
        "input_price": float(config.get("input_price", 0.0)),
        "output_price": float(config.get("output_price", 0.0)),
        "price_unit": int(config.get("price_unit", DEFAULT_PRICE_UNIT)),
    }


async def public_config() -> dict:
    return public_view(await get_raw_config())


async def resolved_config() -> dict:
    """返回可直接用于发起请求的配置（含解密后的密钥，仅内存中使用）。"""
    config = await get_raw_config()
    if not config:
        raise ApiError(400, "model config is not set, please configure it first")
    api_key = decrypt_secret(config.get("api_key_enc", ""))
    if not api_key:
        raise ApiError(400, "stored api_key cannot be decrypted, please configure it again")
    return {
        "provider_url": config["provider_url"],
        "model": config["model"],
        "api_key": api_key,
        "input_price": float(config.get("input_price", 0.0)),
        "output_price": float(config.get("output_price", 0.0)),
        "price_unit": int(config.get("price_unit", DEFAULT_PRICE_UNIT)),
    }
