#!/usr/bin/env python
"""
Run both MCP SSE server and FastAPI health server
"""

import os
import sys
import asyncio
import threading
import logging
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def run_health_server():
    """Run the FastAPI health server in a thread"""
    from src.mcp_server.health_server import run_health_server as start_health
    logger.info("Starting health server thread...")
    # Health server runs on the main MCP port for /health endpoint
    port = int(os.getenv("ARCHON_MCP_PORT", "8051"))
    start_health(host="0.0.0.0", port=port)

def run_mcp_server():
    """Run the main MCP SSE server"""
    logger.info("Starting MCP SSE server...")
    # Import and run the MCP server
    from src.mcp_server.mcp_server import main
    main()

if __name__ == "__main__":
    try:
        # Set SSE transport explicitly
        os.environ["MCP_TRANSPORT"] = "sse"
        
        logger.info("🚀 Starting Archon MCP Service")
        logger.info(f"   Port: {os.getenv('ARCHON_MCP_PORT', '8051')}")
        logger.info("   Transport: SSE")
        logger.info("   Health API: Enabled")
        
        # Start health server in a background thread
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
        
        # Give health server a moment to start
        import time
        time.sleep(2)
        
        # Run MCP server in main thread
        run_mcp_server()
        
    except KeyboardInterrupt:
        logger.info("👋 Shutting down MCP services...")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)