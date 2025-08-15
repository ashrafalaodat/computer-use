"""
FastAPI application for session management backend.
"""

import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from typing import List
import logging
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DBSession
from anthropic import Anthropic

from database import get_db, create_tables
import models
from database import get_db, create_tables
from services.session_service import SessionService
from services.task_service import TaskExecutionService
from services.config_service import ConfigService
from services.websocket_service import websocket_service
from models import AgentConfigResponse, AgentConfigUpdate

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("legent_ai")

# Load environment variables from mounted .env (dev) or real env (prod). Allow overrides for dev hot-reload.
load_dotenv(override=True)

# Initialize Anthropic client
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("lifespan: startup - creating tables")
    create_tables()
    yield
    # Shutdown
    logger.info("lifespan: shutdown")

# Create FastAPI app
app = FastAPI(
    title="Session Management Backend",
    description="Backend system for managing chat sessions with task execution",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# Dependency to get services
def get_session_service(db: DBSession = Depends(get_db)) -> SessionService:
    return SessionService(db)

def get_config_service(db: DBSession = Depends(get_db)) -> ConfigService:
    return ConfigService(db)

def get_task_service(
    session_service: SessionService = Depends(get_session_service),
    config_service: ConfigService = Depends(get_config_service)
) -> TaskExecutionService:
    return TaskExecutionService(anthropic_client, session_service, config_service)

# Root endpoint - serve the frontend
@app.get("/", response_class=FileResponse)
async def read_root():
    logger.debug("GET / -> index.html")
    return FileResponse(os.path.join("static", "index.html"))

# Session Management Endpoints
@app.post("/api/sessions", response_model=models.SessionResponse)
async def create_session(
    session_data: models.SessionCreate,
    session_service: SessionService = Depends(get_session_service),
    config_service: ConfigService = Depends(get_config_service)
):
    """Create a new chat session."""
    logger.info("POST /api/sessions title=%s", session_data.title)
    db_session = session_service.create_session(session_data)
    # Create a default config for the new session
    config = config_service.create_default_config_for_session(db_session)
    # Explicitly construct response to ensure clean JSON
    return models.SessionResponse(
        id=db_session.id,
        title=db_session.title,
        status=db_session.status,
        created_at=db_session.created_at,
        updated_at=db_session.updated_at,
        message_count=0,
        metadata=db_session.metadata_ or {},
        config=config
    )

@app.get("/api/sessions", response_model=List[models.SessionResponse])
def list_sessions(
    limit: int = 50,
    offset: int = 0,
    session_service: SessionService = Depends(get_session_service)
):
    """List all sessions with pagination."""
    logger.debug("GET /api/sessions limit=%s offset=%s", limit, offset)
    sessions = session_service.get_sessions(skip=offset, limit=limit)
    # Manually construct responses to include config
    response = []
    for s in sessions:
        response.append(models.SessionResponse(
            id=s.id,
            title=s.title,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=s.message_count,
            metadata=s.metadata_ or {},
            config=s.config
        ))
    return response

@app.get("/api/sessions/{session_id}", response_model=models.SessionResponse)
async def get_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service)
):
    """Get a specific session by ID."""
    logger.debug("GET /api/sessions/%s", session_id)
    session = session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return models.SessionResponse.model_validate(session)

@app.put("/api/sessions/{session_id}", response_model=models.SessionResponse)
def update_session(
    session_id: str,
    session_data: models.SessionUpdate,
    session_service: SessionService = Depends(get_session_service)
):
    """Update session details."""
    logger.info("PUT /api/sessions/%s", session_id)
    session = session_service.update_session(session_id, session_data)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return models.SessionResponse.model_validate(session)

@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service)
):
    """Delete a session and all its messages."""
    logger.info("DELETE /api/sessions/%s", session_id)
    success = session_service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted successfully"}

# Agent Configuration Endpoints
@app.get("/api/sessions/{session_id}/config", response_model=AgentConfigResponse)
async def get_agent_config(
    session_id: str,
    config_service: ConfigService = Depends(get_config_service),
    session_service: SessionService = Depends(get_session_service),
):
    """Get the agent configuration for a session. If missing, create a default one."""
    logger.debug("GET /api/sessions/%s/config", session_id)
    config = config_service.get_config_by_session_id(session_id)
    if not config:
        session = session_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        config = config_service.create_default_config_for_session(session)
    return config

@app.put("/api/sessions/{session_id}/config", response_model=AgentConfigResponse)
async def update_agent_config(
    session_id: str,
    config_data: AgentConfigUpdate,
    config_service: ConfigService = Depends(get_config_service)
):
    """Update the agent configuration for a session."""
    logger.info("PUT /api/sessions/%s/config", session_id)
    config = config_service.update_config(session_id, config_data)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found for this session.")
    return config


# Message Management Endpoints
@app.post("/api/sessions/{session_id}/messages", response_model=models.MessageResponse)
def add_message(
    session_id: str,
    message_data: models.MessageCreate,
    session_service: SessionService = Depends(get_session_service)
):
    """Add a message to a session."""
    logger.info("POST /api/sessions/%s/messages", session_id)
    message = session_service.add_message_to_session(
        session_id,
        message_data,
        message_type=models.MessageType.USER,
        is_internal=False
    )
    if not message:
        raise HTTPException(status_code=404, detail="Session not found")
    return message

@app.get("/api/sessions/{session_id}/messages", response_model=List[models.MessageResponse])
async def get_session_messages(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    session_service: SessionService = Depends(get_session_service)
):
    """Get messages for a session."""
    logger.debug("GET /api/sessions/%s/messages limit=%s offset=%s", session_id, limit, offset)
    messages = session_service.get_messages_for_session(session_id, skip=offset, limit=limit)
    return [models.MessageResponse.model_validate(msg) for msg in messages]

# Task Execution Endpoints
@app.post("/api/tasks/execute")
async def execute_task(
    task_request: models.TaskRequest,
    task_service: TaskExecutionService = Depends(get_task_service)
):
    """Execute a task asynchronously."""
    logger.info("POST /api/tasks/execute session_id=%s", task_request.session_id)
    task_id = await task_service.execute_task(task_request)
    return {"task_id": task_id, "status": "started"}

# WebSocket endpoint for real-time updates
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    logger.info("WS connect session_id=%s", session_id)
    await websocket_service.connect(websocket, session_id)
    try:
        while True:
            # Keep the connection alive, but we don't need to process incoming messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WS disconnect session_id=%s", session_id)
        websocket_service.disconnect(websocket, session_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
