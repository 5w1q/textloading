import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models import TaskStatus


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: int
    email: EmailStr

    model_config = {"from_attributes": True}


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
    charged_at: datetime | None = None
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
