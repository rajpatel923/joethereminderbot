from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    id: int
    role: str
    content: str
    timestamp: datetime


@dataclass
class Note:
    id: int
    content: str
    created_at: datetime


@dataclass
class Reminder:
    id: int
    content: str
    remind_at: datetime
    sent: bool
    created_at: datetime
    reminder_type: str = "single"
    needs_followup: bool = False


@dataclass
class PendingFollowup:
    id: int
    reminder_content: str
    asked_at: datetime
    resolved: bool
