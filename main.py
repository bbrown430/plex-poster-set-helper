# main.py
import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from config import Settings
from plex_service import PlexService
from scrapers import process_url

app = FastAPI()
settings = Settings()
logger = logging.getLogger(__name__)

# Initialize Plex connection on startup
@app.on_event("startup")
async def startup_event():
    try:
        app.state.plex_service = PlexService(settings)
        logger.info("Plex connection initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Plex: {str(e)}")
        raise RuntimeError("Plex initialization failed")

@app.post("/upload/url")
async def upload_url(
    background_tasks: BackgroundTasks,  # BackgroundTasks comes first
    url: str  # Required parameter without default
):
    """Process a single poster set URL"""
    if not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL format")
    
    background_tasks.add_task(
        process_url,
        url,
        app.state.plex_service.tv_libraries,
        app.state.plex_service.movie_libraries
    )
    return JSONResponse(
        content={"status": "accepted", "message": "Processing URL in background"}
    )

def is_valid_url(url: str) -> bool:
    """Validate supported URLs"""
    supported_domains = ["theposterdb.com", "mediux.pro"]
    return any(domain in url for domain in supported_domains)

def is_not_comment(url: str) -> bool:
    """Check if URL is not a comment"""
    return not url.startswith(("//", "#")) and bool(url.strip())