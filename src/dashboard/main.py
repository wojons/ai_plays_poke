"""
PTP-01X Observability Dashboard - FastAPI Server

Real-time monitoring and control interface for the Pokémon AI system.
Provides REST endpoints and WebSocket streaming for:
- Session status and metrics
- Screenshot viewing
- Command history
- Session control (pause/resume/stop)
"""

import asyncio
import base64
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from src.db.database import GameDatabase
from src.core.screenshot_manager import ScreenshotManager

API_KEY = os.getenv("PTP_API_KEY", "ptp-secret-key-12345")

sessions: Dict[str, Dict[str, Any]] = {}
connection_manager: Dict[str, WebSocket] = {}


def verify_api_key(x_api_key: str = Header(None)) -> bool:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    sessions.clear()
    connection_manager.clear()
    yield


app = FastAPI(
    title="PTP-01X Observability Dashboard",
    description="Real-time monitoring and control for PTP-01X Pokémon AI",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DashboardSession:
    def __init__(self, session_id: str, save_dir: str = "./game_saves"):
        self.session_id = session_id
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.db = GameDatabase(str(self.save_dir / "game_data.db"))
        self.screenshot_manager = ScreenshotManager(str(self.save_dir / "screenshots"))
        self.state = {
            "running": False,
            "paused": False,
            "tick_count": 0,
            "current_state": "idle",
            "location": "Unknown",
            "start_time": None,
            "last_action_time": None
        }
        self.command_history: List[Dict[str, Any]] = []
        self._tick_rate_window: List[float] = []
        self._last_tick_time = time.time()

    def start(self):
        self.state["running"] = True
        self.state["paused"] = False
        self.state["start_time"] = datetime.now().isoformat()
        self._last_tick_time = time.time()

    def pause(self):
        if self.state["running"]:
            self.state["paused"] = True

    def resume(self):
        if self.state["running"]:
            self.state["paused"] = False

    def stop(self):
        self.state["running"] = False
        self.state["paused"] = False

    def update_tick(self, new_state: Optional[str] = None, location: Optional[str] = None):
        current_time = time.time()
        delta = current_time - self._last_tick_time
        self._tick_rate_window.append(delta)
        if len(self._tick_rate_window) > 60:
            self._tick_rate_window.pop(0)
        self._last_tick_time = current_time
        self.state["tick_count"] += 1
        if new_state:
            self.state["current_state"] = new_state
        if location:
            self.state["location"] = location
        self.state["last_action_time"] = datetime.now().isoformat()

    def add_command(self, command: Dict[str, Any]):
        self.command_history.append({
            **command,
            "timestamp": datetime.now().isoformat(),
            "tick": self.state["tick_count"]
        })
        if len(self.command_history) > 1000:
            self.command_history = self.command_history[-1000:]

    def get_status(self) -> Dict[str, Any]:
        elapsed = 0.0
        if self.state["start_time"]:
            start = datetime.fromisoformat(self.state["start_time"])
            elapsed = (datetime.now() - start).total_seconds()

        avg_tick_rate = 0.0
        if self._tick_rate_window:
            avg_tick_rate = len(self._tick_rate_window) / sum(self._tick_rate_window)

        return {
            "session_id": self.session_id,
            "running": self.state["running"],
            "paused": self.state["paused"],
            "elapsed_seconds": elapsed,
            "tick_count": self.state["tick_count"],
            "tick_rate_avg": avg_tick_rate,
            "current_state": self.state["current_state"],
            "location": self.state["location"],
            "start_time": self.state["start_time"],
            "last_action_time": self.state["last_action_time"]
        }

    def get_metrics(self) -> Dict[str, Any]:
        total_cost = 0.0
        total_commands = len(self.command_history)
        success_count = sum(1 for c in self.command_history if c.get("success", True))
        avg_confidence = 0.0
        if self.command_history:
            confidences = [c.get("confidence", 0) for c in self.command_history if c.get("confidence")]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        elapsed = 0.0
        if self.state["start_time"]:
            start = datetime.fromisoformat(self.state["start_time"])
            elapsed = (datetime.now() - start).total_seconds()

        avg_tick_rate = 0.0
        if self._tick_rate_window:
            avg_tick_rate = len(self._tick_rate_window) / sum(self._tick_rate_window)

        return {
            "ticks_per_second": round(avg_tick_rate, 2),
            "total_ticks": self.state["tick_count"],
            "total_commands": total_commands,
            "commands_per_minute": round(total_commands / (elapsed / 60), 2) if elapsed > 0 else 0,
            "success_rate": round(success_count / total_commands, 4) if total_commands > 0 else 1.0,
            "avg_confidence": round(avg_confidence, 4),
            "total_cost_estimate": round(total_cost, 6),
            "elapsed_seconds": round(elapsed, 2),
            "session_active": self.state["running"] and not self.state["paused"]
        }

    def get_recent_actions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.command_history[-limit:]

    def get_latest_screenshot_path(self) -> Optional[Path]:
        return self.screenshot_manager.get_latest_screenshot()


dashboard_sessions: Dict[str, DashboardSession] = {}


def get_session(session_id: str = "default") -> DashboardSession:
    if session_id not in dashboard_sessions:
        dashboard_sessions[session_id] = DashboardSession(session_id)
    return dashboard_sessions[session_id]


@app.get("/")
async def root():
    return FileResponse("src/dashboard/static/index.html")


@app.get("/status")
async def get_status(x_api_key: bool = Depends(verify_api_key), session_id: str = "default"):
    session = get_session(session_id)
    return session.get_status()


@app.get("/screenshots/latest")
async def get_latest_screenshot(
    x_api_key: bool = Depends(verify_api_key),
    session_id: str = "default",
    format: str = "json"
):
    session = get_session(session_id)
    screenshot_path = session.get_latest_screenshot_path()
    
    if not screenshot_path:
        return JSONResponse(content={"error": "No screenshots available"}, status_code=404)
    
    if format == "base64":
        try:
            with open(screenshot_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode()
            return {
                "image": f"data:image/png;base64,{encoded}",
                "path": str(screenshot_path),
                "timestamp": datetime.fromtimestamp(screenshot_path.stat().st_mtime).isoformat()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read screenshot: {e}")
    else:
        return {
            "path": str(screenshot_path),
            "url": f"/screenshots/file?path={screenshot_path}",
            "timestamp": datetime.fromtimestamp(screenshot_path.stat().st_mtime).isoformat()
        }


@app.get("/screenshots/file")
async def get_screenshot_file(path: str = Query(...)):
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(str(p))


@app.get("/actions/recent")
async def get_recent_actions(
    x_api_key: bool = Depends(verify_api_key),
    session_id: str = "default",
    limit: int = 50
):
    session = get_session(session_id)
    return {
        "actions": session.get_recent_actions(limit),
        "total_count": len(session.command_history)
    }


@app.get("/metrics")
async def get_metrics(x_api_key: bool = Depends(verify_api_key), session_id: str = "default"):
    session = get_session(session_id)
    return session.get_metrics()


@app.post("/control/pause")
async def pause_session(x_api_key: bool = Depends(verify_api_key), session_id: str = "default"):
    session = get_session(session_id)
    if not session.state["running"]:
        return JSONResponse(content={"error": "Session not running"}, status_code=400)
    session.pause()
    return {"status": "paused", "session_id": session_id}


@app.post("/control/resume")
async def resume_session(x_api_key: bool = Depends(verify_api_key), session_id: str = "default"):
    session = get_session(session_id)
    if not session.state["running"]:
        return JSONResponse(content={"error": "Session not running"}, status_code=400)
    session.resume()
    return {"status": "resumed", "session_id": session_id}


@app.post("/control/stop")
async def stop_session(x_api_key: bool = Depends(verify_api_key), session_id: str = "default"):
    session = get_session(session_id)
    session.stop()
    return {"status": "stopped", "session_id": session_id}


@app.post("/control/start")
async def start_session(
    x_api_key: bool = Depends(verify_api_key),
    session_id: str = "default",
    save_dir: str = "./game_saves"
):
    if session_id in dashboard_sessions:
        dashboard_sessions[session_id].stop()
    dashboard_sessions[session_id] = DashboardSession(session_id, save_dir)
    dashboard_sessions[session_id].start()
    return {"status": "started", "session_id": session_id}


@app.post("/control/command")
async def send_command(
    command: Dict[str, Any],
    x_api_key: bool = Depends(verify_api_key),
    session_id: str = "default"
):
    session = get_session(session_id)
    if not session.state["running"] or session.state["paused"]:
        return JSONResponse(content={"error": "Session not running"}, status_code=400)
    
    command_entry = {
        "command": command.get("command", "unknown"),
        "reasoning": command.get("reasoning", ""),
        "confidence": command.get("confidence", 0.0),
        "success": True
    }
    session.add_command(command_entry)
    return {"status": "queued", "command": command}


@app.get("/sessions")
async def list_sessions(x_api_key: bool = Depends(verify_api_key)):
    return {
        "sessions": [
            {
                "session_id": sid,
                **sess.get_status()
            }
            for sid, sess in dashboard_sessions.items()
        ]
    }


@app.websocket("/ws/screenshots/{session_id}")
async def websocket_screenshot(websocket: WebSocket, session_id: str):
    await websocket.accept()
    
    if session_id not in dashboard_sessions:
        dashboard_sessions[session_id] = DashboardSession(session_id)
    
    session = dashboard_sessions[session_id]
    connection_manager[session_id] = websocket
    
    try:
        last_screenshot_time = 0
        while True:
            screenshot_path = session.get_latest_screenshot_path()
            
            if screenshot_path and screenshot_path.stat().st_mtime > last_screenshot_time:
                last_screenshot_time = screenshot_path.stat().st_mtime
                try:
                    with open(screenshot_path, "rb") as f:
                        encoded = base64.b64encode(f.read()).decode()
                    
                    await websocket.send_json({
                        "type": "screenshot",
                        "image": f"data:image/png;base64,{encoded}",
                        "path": str(screenshot_path),
                        "timestamp": datetime.fromisoformat(
                            datetime.fromtimestamp(last_screenshot_time).isoformat()
                        ).isoformat(),
                        "tick": session.state["tick_count"],
                        "state": session.state["current_state"]
                    })
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
            
            status = session.get_status()
            metrics = session.get_metrics()
            
            await websocket.send_json({
                "type": "status",
                "tick": status["tick_count"],
                "state": status["current_state"],
                "paused": status["paused"],
                "tick_rate": metrics["ticks_per_second"]
            })
            
            await asyncio.sleep(0.5)
            
    except WebSocketDisconnect:
        if session_id in connection_manager:
            del connection_manager[session_id]


@app.websocket("/ws/metrics/{session_id}")
async def websocket_metrics(websocket: WebSocket, session_id: str):
    await websocket.accept()
    
    if session_id not in dashboard_sessions:
        dashboard_sessions[session_id] = DashboardSession(session_id)
    
    session = dashboard_sessions[session_id]
    
    try:
        while True:
            metrics = session.get_metrics()
            await websocket.send_json({
                "type": "metrics",
                **metrics
            })
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/docs")
async def api_docs():
    return {
        "title": "PTP-01X Dashboard API",
        "version": "1.0.0",
        "endpoints": {
            "GET /status": "Get current session status",
            "GET /screenshots/latest": "Get latest screenshot",
            "GET /actions/recent": "Get recent command history",
            "GET /metrics": "Get performance metrics",
            "POST /control/pause": "Pause session",
            "POST /control/resume": "Resume session",
            "POST /control/stop": "Stop session",
            "POST /control/start": "Start new session",
            "POST /control/command": "Queue a command",
            "GET /sessions": "List all sessions",
            "WS /ws/screenshots/{id}": "Real-time screenshot stream",
            "WS /ws/metrics/{id}": "Real-time metrics stream"
        }
    }


def create_dashboard_app(save_dir: str = "./game_saves") -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PTP_DASHBOARD_PORT", "8000"))
    host = os.getenv("PTP_DASHBOARD_HOST", "0.0.0.0")
    
    print(f"Starting PTP-01X Dashboard on {host}:{port}")
    print(f"API Key: {API_KEY}")
    print(f"Documentation: http://{host}:{port}/api/docs")
    
    uvicorn.run(app, host=host, port=port)