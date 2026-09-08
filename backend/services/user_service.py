"""用户服务：注册、认证、权限、统计。"""
from __future__ import annotations

import time
from datetime import datetime

from backend import config
from backend.core.responses import ApiError
from backend.core.security import hash_password, verify_password
from backend.core.storage import users_store


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _public(user: dict, stats: dict | None = None) -> dict:
    """对外暴露的用户信息，绝不包含密码哈希。"""
    stats = stats or {"submit_count": 0, "resolve_count": 0}
    return {
        "user_id": str(user["user_id"]),
        "username": user["username"],
        "join_time": user.get("join_time", _today()),
        "role": user.get("role", "user"),
        "submit_count": int(stats.get("submit_count", 0)),
        "resolve_count": int(stats.get("resolve_count", 0)),
    }


def validate_username(username: str) -> str:
    if not isinstance(username, str):
        raise ApiError(400, "username must be a string")
    name = username.strip()
    if len(name) < config.USERNAME_MIN_LEN or len(name) > config.USERNAME_MAX_LEN:
        raise ApiError(400, f"username length must be between {config.USERNAME_MIN_LEN} and {config.USERNAME_MAX_LEN}")
    if any(ch.isspace() for ch in name):
        raise ApiError(400, "username must not contain whitespace")
    return name


def validate_password(password: str) -> str:
    if not isinstance(password, str):
        raise ApiError(400, "password must be a string")
    if len(password) < config.PASSWORD_MIN_LEN:
        raise ApiError(400, f"password must be at least {config.PASSWORD_MIN_LEN} characters")
    return password


async def ensure_initial_admin() -> dict:
    """系统启动时确保存在初始管理员。"""
    data = await users_store.read()
    for user in data.get("users", {}).values():
        if user.get("username") == config.ADMIN_USERNAME:
            return user
    return await create_user(config.ADMIN_USERNAME, config.ADMIN_PASSWORD, role="admin")


async def create_user(username: str, password: str, role: str = "user") -> dict:
    username = validate_username(username)
    password = validate_password(password)
    if role not in config.VALID_ROLES:
        raise ApiError(400, f"invalid role: {role}")

    result: dict = {}

    def mutate(data: dict) -> dict:
        users = data.setdefault("users", {})
        for user in users.values():
            if user.get("username") == username:
                raise ApiError(400, "username already exists")
        new_id = str(data.get("next_id", 1))
        data["next_id"] = int(new_id) + 1
        user = {
            "user_id": new_id,
            "username": username,
            "password_hash": hash_password(password),
            "role": role,
            "join_time": _today(),
            "created_at": time.time(),
        }
        users[new_id] = user
        result["user"] = user
        return data

    await users_store.update(mutate)
    return result["user"]


async def get_user(user_id: str) -> dict | None:
    data = await users_store.read()
    return data.get("users", {}).get(str(user_id))


async def get_user_by_name(username: str) -> dict | None:
    data = await users_store.read()
    for user in data.get("users", {}).values():
        if user.get("username") == username:
            return user
    return None


async def authenticate(username: str, password: str) -> dict:
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        raise ApiError(400, "username and password are required")
    user = await get_user_by_name(username)
    if user is None or not verify_password(password, user.get("password_hash", "")):
        raise ApiError(401, "invalid username or password")
    if user.get("role") == "banned":
        raise ApiError(403, "user is banned")
    return user


async def set_role(user_id: str, role: str) -> dict:
    if role not in config.VALID_ROLES:
        raise ApiError(400, f"invalid role: {role}; valid roles are {', '.join(config.VALID_ROLES)}")
    found: dict = {}

    def mutate(data: dict) -> dict:
        user = data.get("users", {}).get(str(user_id))
        if user is None:
            raise ApiError(404, "user not found")
        user["role"] = role
        found["user"] = user
        return data

    await users_store.update(mutate)
    return found["user"]


async def all_users() -> list[dict]:
    data = await users_store.read()
    users = list(data.get("users", {}).values())
    users.sort(key=lambda u: int(u.get("user_id", 0)))
    return users


async def resolve_user_ref(ref: str) -> str | None:
    """把 user_id 或 username 解析成 user_id；找不到返回 None。"""
    if ref is None:
        return None
    data = await users_store.read()
    users = data.get("users", {})
    if str(ref) in users:
        return str(ref)
    for user in users.values():
        if user.get("username") == ref:
            return str(user["user_id"])
    return None


async def list_users(page: int | None, page_size: int | None) -> tuple[int, list[dict]]:
    from backend.core.pagination import paginate, parse_pagination

    page, page_size = parse_pagination(page, page_size)
    users = await all_users()
    return len(users), paginate(users, page, page_size)


async def public_user(user: dict, stats: dict | None = None) -> dict:
    if stats is None:
        from backend.services import stats_service

        stats = await stats_service.user_stats(str(user["user_id"]))
    return _public(user, stats)


async def public_users(users: list[dict]) -> list[dict]:
    """批量转换，避免每个用户都扫描一遍提交记录。"""
    from backend.services import stats_service

    stats = await stats_service.all_user_stats()
    return [_public(u, stats.get(str(u["user_id"]), {"submit_count": 0, "resolve_count": 0})) for u in users]


async def clear_users() -> None:
    await users_store.write({"next_id": 1, "users": {}})
