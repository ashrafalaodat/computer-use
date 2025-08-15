"""
Session management service layer.
"""

import uuid
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
import models
from models import SessionStatus, MessageType

class SessionService:
    def __init__(self, db: Session):
        self.db = db

    def create_session(self, session_data: models.SessionCreate) -> models.Session:
        session_id = str(uuid.uuid4())
        db_session = models.Session(
            id=session_id,
            title=session_data.title,
            status=SessionStatus.ACTIVE.value,
            metadata_=session_data.metadata_
        )
        
        self.db.add(db_session)
        self.db.commit()
        self.db.refresh(db_session)
        return db_session

    def get_session(self, session_id: str) -> Optional[models.Session]:
        return self.db.query(models.Session).filter(models.Session.id == session_id).first()

    def get_sessions(self, skip: int = 0, limit: int = 100) -> List[models.SessionResponse]:
        sessions = self.db.query(models.Session).order_by(models.Session.created_at.desc()).offset(skip).limit(limit).all()
        
        results = []
        for session in sessions:
            message_count = self.db.query(func.count(models.Message.id)).filter(models.Message.session_id == session.id).scalar()
            session_data = {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "status": session.status,
                "message_count": message_count,
                "metadata": dict(session.metadata_) if session.metadata_ else {}
            }
            results.append(models.SessionResponse(**session_data))
            
        return results

    def update_session(self, session_id: str, session_data: models.SessionUpdate) -> Optional[models.Session]:
        session = self.get_session(session_id)
        if session:
            update_data = session_data.model_dump(exclude_unset=True, by_alias=True)
            for key, value in update_data.items():
                if key == 'metadata': # handle the alias
                    key = 'metadata_'
                setattr(session, key, value)
            
            self.db.commit()
            self.db.refresh(session)
        return session

    def delete_session(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        if session:
            self.db.delete(session)
            self.db.commit()
            return True
        return False

    def add_message_to_session(self, session_id: str, message_data: models.MessageCreate, message_type: MessageType, is_internal: bool = False) -> Optional[models.Message]:
        session = self.get_session(session_id)
        if not session:
            return None

        message_id = str(uuid.uuid4())
        db_message = models.Message(
            id=message_id,
            session_id=session_id,
            content=message_data.content,
            message_type=message_type.value,
        )
        self.db.add(db_message)
        self.db.commit()
        self.db.refresh(db_message)
        return db_message

    def get_messages_for_session(self, session_id: str, skip: int = 0, limit: int = 1000) -> List[models.Message]:
        return (
            self.db
            .query(models.Message)
            .filter(models.Message.session_id == session_id)
            .order_by(models.Message.timestamp)
            .offset(skip)
            .limit(limit)
            .all()
        )
