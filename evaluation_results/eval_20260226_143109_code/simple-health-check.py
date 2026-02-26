# Task: simple-health-check
# Pipeline status: approved
# Target file: app/api/routes/health_endpoint.py

# health_endpoint.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def get_health() -> dict:
    return {"status": "ok"}