"""Hubfeed Agent - Main FastAPI application."""

import logging
import sys
import os
import argparse
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.__version__ import __version__
from src.config import ConfigManager
from src.core import HubfeedClient, JobExecutor, AgentLoop
from src.history import HistoryLogger
from src.platforms import PlatformManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('agent.log')
    ]
)

logger = logging.getLogger(__name__)

# Global instances
config_manager: ConfigManager = None
hubfeed_client: HubfeedClient = None
history_logger: HistoryLogger = None
executor: JobExecutor = None
agent_loop: AgentLoop = None
platform_manager: PlatformManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global config_manager, hubfeed_client, history_logger, executor, agent_loop, platform_manager
    
    logger.info(f"Starting Hubfeed Agent v{__version__}")
    
    # Initialize data directory
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    # Initialize components    
    history_logger = HistoryLogger(data_dir)
    logger.info("History logger initialized")

    config_manager = ConfigManager(data_dir, history_logger=history_logger)
    logger.info("Configuration manager initialized")
    
    
    hubfeed_client = HubfeedClient(config_manager)
    logger.info("Hubfeed client initialized")
    
    executor = JobExecutor(config_manager, history_logger)
    logger.info("Job executor initialized")
    
    agent_loop = AgentLoop(config_manager, hubfeed_client, executor)
    logger.info("Agent loop initialized")
    
    platform_manager = PlatformManager(config_manager)
    logger.info("Platform manager initialized")
    
    # Start polling loop if configured
    if config_manager.is_configured():
        logger.info("Agent is configured, starting polling loop...")
        await agent_loop.start()
    else:
        logger.warning(
            "Agent not configured. Please configure agent token via web UI."
        )
    
    logger.info("Hubfeed Agent started successfully")    
    history_logger.log_system_event(f"Starting Hubfeed Agent v{__version__}", "system", "", actor="system")
    yield
    
    # Shutdown
    logger.info("Shutting down Hubfeed Agent...")
    history_logger.log_system_event("Shutting down Hubfeed Agent...", "system", "", actor="system")
    
    if agent_loop:
        await agent_loop.stop()
    
    if platform_manager:
        await platform_manager.disconnect_all()
    
    logger.info("Hubfeed Agent stopped")


# Create FastAPI app
app = FastAPI(
    title="Hubfeed Agent",
    description="Local agent for BYOD (Bring Your Own Data) access to private sources",
    version=__version__,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local use only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
from .api import routes as api_routes

app.include_router(api_routes.router, prefix="/api")

# Mount static files (UI) - will be created later
ui_dir = Path(__file__).parent.parent / "ui"
if ui_dir.exists():
    app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")
else:
    logger.warning(f"UI directory not found at {ui_dir}")
    
    # Provide a simple root endpoint
    @app.get("/")
    async def root():
        return {
            "name": "Hubfeed Agent",
            "version": __version__,
            "status": "running",
            "message": "UI not available. API accessible at /api"
        }


@app.get("/health")
async def health():
    """Health check endpoint."""
    health_status = await agent_loop.health_check() if agent_loop else {}
    
    return {
        "status": "healthy" if agent_loop and agent_loop.is_running else "degraded",
        "version": __version__,
        "agent": health_status
    }


def main():
    """Main entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Hubfeed Agent - Local data collection agent')
    parser.add_argument(
        '--username',
        type=str,
        help='Override AGENT_UI_USERNAME environment variable'
    )
    parser.add_argument(
        '--password',
        type=str,
        help='Override AGENT_UI_PASSWORD environment variable'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8080,
        help='Port to bind to (default: 8080)'
    )
    
    args = parser.parse_args()
    
    # Override environment variables if provided via CLI
    if args.username:
        os.environ['AGENT_UI_USERNAME'] = args.username
        logger.info(f"Username set via CLI argument: {args.username}")
    
    if args.password:
        os.environ['AGENT_UI_PASSWORD'] = args.password
        logger.info(f"Password set via CLI argument: {args.password}")
    
    # Start the server
    uvicorn.run(
        "src.main:app",
        host=args.host,
        port=args.port,
        reload=False,  # Set to True for development
        log_level="info"
    )


if __name__ == "__main__":
    main()
