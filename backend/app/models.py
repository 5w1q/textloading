import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    # 已写入部分链接后中断（超时、上游错误等），与 failed 区分
    partial = "partial"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tasks: Mapped[list["SyncTask"]] = relationship(back_populates="user")
    videos: Mapped[list["UserVideo"]] = relationship(back_populates="user")


class UniqueIdMapping(Base):
    __tablename__ = "unique_id_mappings"

    unique_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sec_uid: Mapped[str] = mapped_column(String(128), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SyncTask(Base):
    __tablename__ = "sync_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    unique_id: Mapped[str] = mapped_column(String(128), index=True)
    sec_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=32),
        default=TaskStatus.pending,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_links_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="tasks")


class UserVideo(Base):
    __tablename__ = "user_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    unique_id: Mapped[str] = mapped_column(String(128), index=True)
    sec_uid: Mapped[str] = mapped_column(String(128), index=True)
    aweme_id: Mapped[str] = mapped_column(String(64), index=True)
    share_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sync_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user: Mapped["User"] = relationship(back_populates="videos")

    __table_args__ = (UniqueConstraint("user_id", "aweme_id", name="uq_user_video_aweme"),)
