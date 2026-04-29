import hashlib

from app.adapters.base import PostItem, PostPage


def _fake_sec_uid(unique_id: str) -> str:
    h = hashlib.sha256(unique_id.encode()).hexdigest()[:32]
    return f"MS4wLjABAAAA{h}"


def _fake_numeric_aweme_id(unique_id: str, page: int, index: int) -> str:
    """生成 19 位数字形态假 aweme_id（仅供联调；抖音站内需真实作品 ID 才能打开）。"""
    digest = hashlib.sha256(f"{unique_id}:{page}:{index}".encode()).hexdigest()
    n = int(digest[:14], 16) % 9_000_000_000_000_000_000
    return str(7_300_000_000_000_000_000 + n)


class MockDouyinAdapter:
    """本地联调用：生成分页假数据，行为与真实游标分页一致。

    注意：`share_url` 为演示数据，**无法在** https://www.douyin.com **打开**。
    真实可点链接需 `DOUYIN_ADAPTER=http` 并对接真实解析服务。
    """

    page_size = 20
    max_pages = 15

    async def resolve_sec_uid(self, unique_id: str) -> str:
        return _fake_sec_uid(unique_id)

    async def fetch_user_post_page(self, sec_uid: str, cursor: str | None) -> PostPage:
        page = int(cursor) if cursor else 0
        unique_hint = sec_uid[-8:] if len(sec_uid) >= 8 else sec_uid
        items = [
            PostItem(
                aweme_id=(aid := _fake_numeric_aweme_id(unique_hint, page, i)),
                share_url=f"https://www.douyin.com/video/{aid}",
            )
            for i in range(self.page_size)
        ]
        next_page = page + 1
        has_more = page < self.max_pages - 1
        next_cursor = str(next_page) if has_more else None
        return PostPage(items=items, next_cursor=next_cursor, has_more=has_more)
