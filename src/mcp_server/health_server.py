"""
FastAPI Health Server for MCP
Provides HTTP health endpoints while MCP runs on SSE transport
"""

import asyncio
import json
import time
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="Archon MCP Health Server")

# Track server startup time
startup_time = time.time()

@app.get("/health")
async def health():
    """Health check endpoint for archon-server to query"""
    uptime = time.time() - startup_time
    return JSONResponse(content={
        "status": "running",
        "uptime": uptime,
        "uptime_seconds": uptime,
        "service": "archon-mcp",
        "transport": "sse",
        "timestamp": datetime.now().isoformat(),
        "health": {
            "status": "healthy",
            "api_service": True,
            "last_health_check": datetime.now().isoformat()
        }
    })

@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "archon-mcp-health", "status": "running"}

@app.get("/clients")
async def get_clients():
    """Get connected MCP clients"""
    return {
        "clients": [],
        "total": 0,
        "message": "Client tracking not implemented for SSE transport"
    }

@app.get("/sessions")
async def get_sessions():
    """Get MCP sessions"""
    uptime = time.time() - startup_time
    return {
        "active_sessions": 0,
        "session_timeout": 3600,
        "server_uptime_seconds": uptime
    }

def run_health_server(host="0.0.0.0", port=8052):
    """Run the health server on a different port"""
    logger.info(f"Starting FastAPI health server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="error")

if __name__ == "__main__":
    run_health_server()