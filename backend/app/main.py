"""
FastAPI main entry point for the Broccoli Crown Detection app.

This file starts the API server and connects all the routes.
The YOLOv8n model is loaded one time at startup, so the server
does not need to load it again for every request.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import detect, health
from app.services.detector import BroccoliDetector


# Path to the trained YOLOv8n weights file.
# In Deliverable B we trained the model and saved best.pt here.
WEIGHTS_PATH = Path(__file__).parent.parent / "weights" / "best.pt"

# Folder where uploaded images are saved.
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler.

    Code before 'yield' runs at startup.
    Code after 'yield' runs at shutdown.
    """
    # Load the YOLOv8n model into memory one time.
    # We store it on app.state so any route can use it.
    print(f"Loading YOLOv8n model from: {WEIGHTS_PATH}")
    app.state.detector = BroccoliDetector(weights_path=str(WEIGHTS_PATH))
    print("Model loaded. API is ready.")

    yield

    # Clean up at shutdown (nothing to do for now).
    print("API is shutting down.")


# Create the FastAPI app and pass the lifespan handler.
app = FastAPI(
    title="Broccoli Crown Detection API",
    description="A small API that finds broccoli crowns in field images "
                "and estimates the size of each crown.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the React frontend (which runs on a different port) to call this API.
# In a real deployment we would limit allow_origins to the real frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded and result images as static files so the frontend can show them.
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Connect the route files.
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(detect.router, prefix="/api", tags=["detect"])


@app.get("/")
def root():
    """Simple welcome message at the root URL."""
    return {
        "message": "Broccoli Crown Detection API is running.",
        "docs": "/docs",
    }
