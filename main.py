import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from config import Settings
from plex_service import PlexService
from scrapers import process_url

# Load settings
settings = Settings()
logger = logging.getLogger(__name__)

# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.plex_service = PlexService(settings)
        logger.info("Plex connection initialized successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize Plex: {str(e)}")
        raise RuntimeError("Plex initialization failed")

# Initialize FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this for security in production
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

@app.post("/upload/url")
async def upload_url(url: str, quality: str):
    """Process a single poster set URL synchronously and return its result"""
    if not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL format")
    
    try:
        app.state.plex_service.filter_libraries(quality=quality)

        # Process the URL and get the result synchronously
        result = process_url(
            url, 
            app.state.plex_service.tv_libraries, 
            app.state.plex_service.movie_libraries
        )
        return JSONResponse(
            content={"status": "completed", "message": "URL processed successfully", "data": result}
        )
    except Exception as e:
        logger.error(f"Error processing URL: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing URL: {str(e)}")


def is_valid_url(url: str) -> bool:
    """Validate supported URLs"""
    supported_domains = ["theposterdb.com", "mediux.pro"]
    return any(domain in url for domain in supported_domains)

def is_not_comment(url: str) -> bool:
    """Check if URL is not a comment"""
    return not url.startswith(("//", "#")) and bool(url.strip())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=38100)
