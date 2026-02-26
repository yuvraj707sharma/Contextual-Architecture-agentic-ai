# Task: simple-health-check
# Pipeline status: approved
# Target file: app/api/routes/feature.py

# feature.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def get_health():
    """Returns the health status of the application."""
    try:
        return {"status": "ok"}
    except Exception as e:
        # Log the error with context
        # Assuming a logging library is available, but since it's unknown, 
        # we'll use the built-in logging module for demonstration purposes.
        import logging
        logging.error(f"Error in /health endpoint: {str(e)}")
        return {"status": "error", "message": "Internal Server Error"}