"""
Service for managing WebSocket connections and broadcasting messages.
"""

import json
from typing import List, Dict, Optional
from fastapi import WebSocket

class WebSocketService:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.session_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: Optional[str] = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        if session_id:
            if session_id not in self.session_connections:
                self.session_connections[session_id] = []
            self.session_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: Optional[str] = None):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if session_id and session_id in self.session_connections:
            if websocket in self.session_connections[session_id]:
                self.session_connections[session_id].remove(websocket)

    async def send_to_session(self, payload: dict, session_id: str):
        """Send a JSON payload to all clients in a specific session."""
        message = json.dumps(payload)
        if session_id in self.session_connections:
            for connection in self.session_connections[session_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    # Handle broken connections if necessary
                    pass

# Singleton instance to be used across the application
websocket_service = WebSocketService()
