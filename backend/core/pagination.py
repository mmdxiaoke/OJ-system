"""分页参数解析（提交列表与用户列表共用）。"""
from __future__ import annotations

from backend.core.responses import ApiError


def parse_pagination(page, page_size) -> tuple[int | None, int | None]:
    """按 API 文档解析分页参数。

    * ``page`` 与 ``page_size`` 均为空 -> 查询全部数据；
    * ``page`` 为空但 ``page_size`` 非空 -> 第一页；
    * ``page`` 非空但 ``page_size`` 为空 -> 参数错误（400）。
    """
    if page is None and page_size is None:
        return None, None
    if page_size is None:
        raise ApiError(400, "page_size is required when page is provided")
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        raise ApiError(400, "page_size must be an integer") from None
    if page_size <= 0:
        raise ApiError(400, "page_size must be positive")
    if page is None:
        return 1, page_size
    try:
        page = int(page)
    except (TypeError, ValueError):
        raise ApiError(400, "page must be an integer") from None
    if page <= 0:
        raise ApiError(400, "page must be positive")
    return page, page_size


def paginate(items: list, page: int | None, page_size: int | None) -> list:
    if page is None and page_size is None:
        return items
    start = (page - 1) * page_size
    return items[start:start + page_size]
