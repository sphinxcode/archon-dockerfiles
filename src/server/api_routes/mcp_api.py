"""
MCP API endpoints for Archon

Provides status and configuration endpoints for the MCP service.
The MCP container is managed by docker-compose (local) or as a microservice (Railway).
"""

import os
from typing import Any
import aiohttp
import asyncio

from fastapi import APIRouter, HTTPException

# Import unified logging
from ..config.logfire_config import api_logger, safe_set_attribute, safe_span

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


async def get_container_status_http() -> dict[str, Any]:
    """Get MCP status via HTTP from the archon-mcp microservice."""
    mcp_url = os.getenv("MCP_SERVER_URL", "").rstrip("/")
    
    if not mcp_url:
        return {
            "status": "error",
            "uptime": None,
            "logs": [],
            "container_status": "error",
            "error": "MCP_SERVER_URL not configured"
        }
    
    try:
        # Try to get status from the MCP microservice
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{mcp_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "status": "running",
                        "uptime": data.get("uptime"),
                        "logs": [],
                        "container_status": "running",
                        "service_info": data
                    }
                else:
                    return {
                        "status": "error",
                        "uptime": None,
                        "logs": [],
                        "container_status": "error",
                        "error": f"MCP service returned status {response.status}"
                    }
    except asyncio.TimeoutError:
        return {
            "status": "error",
            "uptime": None,
            "logs": [],
            "container_status": "timeout",
            "error": "MCP service timeout - service may be starting"
        }
    except Exception as e:
        return {
            "status": "error",
            "uptime": None,
            "logs": [],
            "container_status": "error",
            "error": f"Failed to connect to MCP service: {str(e)}"
        }


def get_container_status_docker() -> dict[str, Any]:
    """Get MCP container status using Docker (for local deployments)."""
    try:
        import docker
        from docker.errors import NotFound
        
        docker_client = None
        try:
            docker_client = docker.from_env()
            container = docker_client.containers.get("archon-mcp")

            # Get container status
            container_status = container.status

            # Map Docker statuses to simple statuses
            if container_status == "running":
                status = "running"
                # Try to get uptime from container info
                try:
                    from datetime import datetime
                    started_at = container.attrs["State"]["StartedAt"]
                    started_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    uptime = int((datetime.now(started_time.tzinfo) - started_time).total_seconds())
                except Exception:
                    uptime = None
            else:
                status = "stopped"
                uptime = None

            return {
                "status": status,
                "uptime": uptime,
                "logs": [],  # No log streaming anymore
                "container_status": container_status
            }

        except NotFound:
            return {
                "status": "not_found",
                "uptime": None,
                "logs": [],
                "container_status": "not_found",
                "message": "MCP container not found. Run: docker compose up -d archon-mcp"
            }
        except Exception as e:
            api_logger.error("Failed to get container status", exc_info=True)
            return {
                "status": "error",
                "uptime": None,
                "logs": [],
                "container_status": "error",
                "error": str(e)
            }
        finally:
            if docker_client is not None:
                try:
                    docker_client.close()
                except Exception:
                    pass
    except ImportError:
        # Docker not available, likely on Railway
        return {
            "status": "error",
            "uptime": None,
            "logs": [],
            "container_status": "no_docker",
            "error": "Docker not available in this environment"
        }


async def get_container_status() -> dict[str, Any]:
    """Get MCP status - tries HTTP first (for Railway), falls back to Docker (for local)."""
    # Check if we have MCP_SERVER_URL configured (Railway deployment)
    if os.getenv("MCP_SERVER_URL"):
        return await get_container_status_http()
    else:
        # Fall back to Docker for local deployments
        return get_container_status_docker()


@router.get("/status")
async def get_status():
    """Get MCP server status."""
    with safe_span("api_mcp_status") as span:
        safe_set_attribute(span, "endpoint", "/api/mcp/status")
        safe_set_attribute(span, "method", "GET")

        try:
            status = await get_container_status()
            api_logger.debug(f"MCP server status checked - status={status.get('status')}")
            safe_set_attribute(span, "status", status.get("status"))
            safe_set_attribute(span, "uptime", status.get("uptime"))
            return status
        except Exception as e:
            api_logger.error(f"MCP server status API failed - error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_mcp_config():
    """Get MCP server configuration."""
    with safe_span("api_get_mcp_config") as span:
        safe_set_attribute(span, "endpoint", "/api/mcp/config")
        safe_set_attribute(span, "method", "GET")

        try:
            api_logger.info("Getting MCP server configuration")

            # Get actual MCP port from environment or use default
            mcp_port = int(os.getenv("ARCHON_MCP_PORT", "8051"))
            
            # Check if we're using HTTP proxy (Railway) or local Docker
            mcp_server_url = os.getenv("MCP_SERVER_URL")
            
            if mcp_server_url:
                # Railway deployment - use proxy URL
                config = {
                    "host": mcp_server_url.replace("http://", "").replace("https://", "").split(":")[0],
                    "port": mcp_port,
                    "transport": "streamable-http",
                    "proxy_url": mcp_server_url,
                    "deployment": "railway"
                }
            else:
                # Local Docker deployment
                config = {
                    "host": "localhost",
                    "port": mcp_port,
                    "transport": "streamable-http",
                    "deployment": "docker"
                }

            # Get only model choice from database (simplified)
            try:
                from ..services.credential_service import credential_service

                model_choice = await credential_service.get_credential(
                    "MODEL_CHOICE", "gpt-4o-mini"
                )
                config["model_choice"] = model_choice
            except Exception:
                # Fallback to default model
                config["model_choice"] = "gpt-4o-mini"

            api_logger.info(f"MCP configuration ({config.get('deployment', 'unknown')} mode)")
            safe_set_attribute(span, "host", config["host"])
            safe_set_attribute(span, "port", config["port"])
            safe_set_attribute(span, "transport", "streamable-http")
            safe_set_attribute(span, "deployment", config.get("deployment", "unknown"))
            safe_set_attribute(span, "model_choice", config.get("model_choice", "gpt-4o-mini"))

            return config
        except Exception as e:
            api_logger.error("Failed to get MCP configuration", exc_info=True)
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail={"error": str(e)})


@router.get("/clients")
async def get_mcp_clients():
    """Get connected MCP clients with type detection."""
    with safe_span("api_mcp_clients") as span:
        safe_set_attribute(span, "endpoint", "/api/mcp/clients")
        safe_set_attribute(span, "method", "GET")

        try:
            # Check if we should query the MCP microservice
            mcp_server_url = os.getenv("MCP_SERVER_URL")
            
            if mcp_server_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{mcp_server_url}/clients", 
                                              timeout=aiohttp.ClientTimeout(total=5)) as response:
                            if response.status == 200:
                                data = await response.json()
                                return {
                                    "clients": data.get("clients", []),
                                    "total": data.get("total", 0)
                                }
                except Exception as e:
                    api_logger.debug(f"Could not get clients from MCP service: {e}")
            
            # Default empty response
            api_logger.debug("Getting MCP clients - returning empty array")
            return {
                "clients": [],
                "total": 0
            }
        except Exception as e:
            api_logger.error(f"Failed to get MCP clients - error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            return {
                "clients": [],
                "total": 0,
                "error": str(e)
            }


@router.get("/sessions")
async def get_mcp_sessions():
    """Get MCP session information."""
    with safe_span("api_mcp_sessions") as span:
        safe_set_attribute(span, "endpoint", "/api/mcp/sessions")
        safe_set_attribute(span, "method", "GET")

        try:
            # Check if we should query the MCP microservice
            mcp_server_url = os.getenv("MCP_SERVER_URL")
            
            if mcp_server_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{mcp_server_url}/sessions",
                                              timeout=aiohttp.ClientTimeout(total=5)) as response:
                            if response.status == 200:
                                return await response.json()
                except Exception as e:
                    api_logger.debug(f"Could not get sessions from MCP service: {e}")
            
            # Basic session info fallback
            status = await get_container_status()

            session_info = {
                "active_sessions": 0,  # TODO: Implement real session tracking
                "session_timeout": 3600,  # 1 hour default
            }

            # Add uptime if server is running
            if status.get("status") == "running" and status.get("uptime"):
                session_info["server_uptime_seconds"] = status["uptime"]

            api_logger.debug(f"MCP session info - sessions={session_info.get('active_sessions')}")
            safe_set_attribute(span, "active_sessions", session_info.get("active_sessions"))

            return session_info
        except Exception as e:
            api_logger.error(f"Failed to get MCP sessions - error={str(e)}")
            safe_set_attribute(span, "error", str(e))
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def mcp_health():
    """Health check for MCP API - used by bug report service and tests."""
    with safe_span("api_mcp_health") as span:
        safe_set_attribute(span, "endpoint", "/api/mcp/health")
        safe_set_attribute(span, "method", "GET")

        # Simple health check - no logging to reduce noise
        result = {"status": "healthy", "service": "mcp"}
        safe_set_attribute(span, "status", "healthy")

        return result