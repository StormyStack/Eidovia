from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================
# USER MANAGEMENT SCHEMAS
# ============================================================

class AdminUserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=8)
    language: str = "en"
    detail_level: int = 1
    is_admin: bool = False


class AdminUserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    detail_level: Optional[int] = None
    language: Optional[str] = None
    is_admin: Optional[bool] = None


class AdminPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8)


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    email: str
    detail_level: int
    language: str
    is_admin: bool
    created_at: Optional[str] = None


# ============================================================
# SUPPORT TICKETS SCHEMAS
# ============================================================

class SupportTicketCreate(BaseModel):
    subject: str = Field(..., min_length=3, max_length=150)
    message: str = Field(..., min_length=5)
    priority: str = Field("medium", pattern="^(low|medium|high)$")


class SupportTicketUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(open|in_progress|resolved)$")
    admin_notes: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(low|medium|high)$")


class SupportTicketResponse(BaseModel):
    ticket_id: str
    user_id: str
    username: str
    subject: str
    message: str
    status: str
    priority: str
    admin_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================================
# SYSTEM MAINTENANCE & ANNOUNCEMENTS SCHEMAS
# ============================================================

class SystemAnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    message: str = Field(..., min_length=5)
    level: str = Field("info", pattern="^(info|warning|critical)$")


class SystemAnnouncementResponse(BaseModel):
    announcement_id: str
    title: str
    message: str
    level: str
    is_active: bool
    created_at: Optional[str] = None


class SystemHealthResponse(BaseModel):
    status: str
    database: dict[str, Any]
    redis: dict[str, Any]
    ai_service: dict[str, Any]
    timestamp: str


class PlatformStatsResponse(BaseModel):
    total_users: int
    admin_users: int
    student_users: int
    total_logs: int
    chat_messages: int
    open_tickets: int
