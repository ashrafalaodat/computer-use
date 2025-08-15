"""
Service for managing agent configurations.
"""

from sqlalchemy.orm import Session as DBSession
import models

class ConfigService:
    def __init__(self, db: DBSession):
        self.db = db

    def get_config_by_session_id(self, session_id: str) -> models.AgentConfig | None:
        """Retrieve the agent configuration for a given session."""
        return self.db.query(models.AgentConfig).filter(models.AgentConfig.session_id == session_id).first()

    def create_default_config_for_session(self, session: models.Session) -> models.AgentConfig:
        """Create a default agent configuration for a new session."""
        config = models.AgentConfig(session_id=session.id)
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def update_config(self, session_id: str, config_data: models.AgentConfigUpdate) -> models.AgentConfig | None:
        """Update the agent configuration for a session."""
        config = self.get_config_by_session_id(session_id)
        if not config:
            return None
        
        update_data = config_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(config, key, value)
            
        self.db.commit()
        self.db.refresh(config)
        return config
