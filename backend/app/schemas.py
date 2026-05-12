import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models import TaskStatus


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: int
    #: 与 Ab 对齐时可能为邮箱或登录名（username）
    email: str

    model_config = {"from_attributes": True}


class AuthMePublic(BaseModel):
    """GET /auth/me：本站用户 id + Ab JWT 中的展示信息（若有）。"""

    id: int
    email: str
    #: 优先 JWT 内自定义昵称等；无则用邮箱
    display_name: str
    is_vip: bool = False
    #: Ab JWT 未带积分字段时为 null
    points_remaining: int | None = None


class SyncTaskCreate(BaseModel):
    unique_id: str = Field(..., min_length=1, max_length=128, description="抖音号，例如 y096031")


class SyncTaskPublic(BaseModel):
    id: uuid.UUID
    unique_id: str
    sec_uid: str | None
    cursor: str | None
    status: TaskStatus
    error_message: str | None
    new_links_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserVideoPublic(BaseModel):
    aweme_id: str
    share_url: str
    unique_id: str
    sec_uid: str
    created_at: datetime
    source_task_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class VideosSummaryPublic(BaseModel):
    """最近一次已完成或部分成功的同步（用于展示「最近采集」）。"""

    last_sync_unique_id: str | None = None
    last_sync_task_id: uuid.UUID | None = None
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None


class UniqueIdRowPublic(BaseModel):
    """当前用户下已采集过的用户标识及条数（用于筛选 / 导出）。"""

    unique_id: str
    video_count: int


class VideoCountPublic(BaseModel):
    total: int


class TaskCountPublic(BaseModel):
    """当前登录用户下的同步任务总条数（用于分页）。"""

    total: int


class DeleteIdentifierResultPublic(BaseModel):
    """删除某用户标识下在本账号内的采集链接与同步任务记录（不影响全局 unique→sec_uid 映射表）。"""

    deleted_videos: int
    deleted_tasks: int
