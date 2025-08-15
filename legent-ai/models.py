"""
Database models for session management system.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field, ConfigDict

from agent.loop import APIProvider
from agent.tools import ToolVersion

Base = declarative_base()

class MessageType(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"

class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"
    PAUSED = "paused"

# SQLAlchemy Models
class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    status = Column(String, default=SessionStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata_ = Column("metadata", JSON, nullable=True, default=dict)
    
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    config = relationship("AgentConfig", uselist=False, back_populates="session", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    message_type = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    metadata_ = Column("metadata", JSON, nullable=True)
    tool_calls = Column(JSON, default=list)
    tool_results = Column(JSON, default=list)

    session = relationship("Session", back_populates="messages")


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, unique=True)
    model = Column(String, default="claude-3-7-sonnet-20250219")
    provider = Column(String, default=APIProvider.ANTHROPIC.value)
    tool_version = Column(String, default="computer_use_20250124")
    system_prompt_suffix = Column(Text, nullable=True)
    max_tokens = Column(Integer, default=4096)
    thinking_budget = Column(Integer, nullable=True, default=2048)
    token_efficient_tools_beta = Column(Boolean, default=False)

    session = relationship("Session", back_populates="config")


# Pydantic Models for API
class SessionBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    metadata_: Optional[Dict[str, Any]] = Field(
        default=None,
        alias='metadata',                # serialize as 'metadata'
        validation_alias='metadata_'     # read from ORM attribute 'metadata_'
    )

class SessionCreate(SessionBase):
    pass

class SessionUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: Optional[str] = None
    status: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = Field(
        default=None,
        alias='metadata',                # name in API
        validation_alias='metadata_'     # read from ORM attribute
    )

class SessionInDBBase(SessionBase):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model: str
    provider: APIProvider
    tool_version: ToolVersion
    system_prompt_suffix: Optional[str] = None
    max_tokens: int
    thinking_budget: Optional[int] = None
    token_efficient_tools_beta: bool

class AgentConfigUpdate(BaseModel):
    model: Optional[str] = None
    provider: Optional[APIProvider] = None
    tool_version: Optional[ToolVersion] = None
    system_prompt_suffix: Optional[str] = None
    max_tokens: Optional[int] = None
    thinking_budget: Optional[int] = None
    token_efficient_tools_beta: Optional[bool] = None

class SessionResponse(SessionInDBBase):
    message_count: int = 0
    config: Optional[AgentConfigResponse] = None

class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    message_type: MessageType
    content: str
    created_at: datetime = Field(validation_alias='timestamp')
    is_internal: bool = False
    metadata_: Optional[Dict[str, Any]] = Field(
        default=None,
        alias='metadata',                # name in API
        validation_alias='metadata_'     # read from ORM attribute
    )

class TaskRequest(BaseModel):
    session_id: str
    task_description: str
    parameters: Optional[dict] = {}

class TaskProgress(BaseModel):
    task_id: str
    session_id: str
    status: str
    progress: float
    current_step: str
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    result: Optional[dict] = None
    error: Optional[str] = None

