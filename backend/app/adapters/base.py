from dataclasses import dataclass
from typing import Protocol


@dataclass
class PostItem:
    aweme_id: str
    share_url: str


@dataclass
class PostPage:
    items: list[PostItem]
    next_cursor: str | None
    has_more: bool


class DouyinAdapter(Protocol):
    async def resolve_sec_uid(self, unique_id: str) -> str: ...

    async def fetch_user_post_page(self, sec_uid: str, cursor: str | None) -> PostPage: ...
