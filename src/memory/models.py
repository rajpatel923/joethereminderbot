from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: int
    telegram_id: int
    timezone: str
    created_at: datetime


@dataclass
class GoogleTokens:
    user_id: int
    access_token: str
    refresh_token: str
    token_expiry: Optional[datetime]


@dataclass
class Message:
    id: int
    role: str
    content: str
    timestamp: datetime
    user_id: Optional[int] = None


@dataclass
class Note:
    id: int
    content: str
    created_at: datetime
    user_id: Optional[int] = None


@dataclass
class Reminder:
    id: int
    content: str
    remind_at: datetime
    sent: bool
    created_at: datetime
    reminder_type: str = "single"
    needs_followup: bool = False
    user_id: Optional[int] = None
    priority: int = 2
    category: str = "general"
    recurrence_rule: Optional[str] = None
    recurrence_end: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None


@dataclass
class PendingFollowup:
    id: int
    reminder_content: str
    asked_at: datetime
    resolved: bool
    user_id: Optional[int] = None
