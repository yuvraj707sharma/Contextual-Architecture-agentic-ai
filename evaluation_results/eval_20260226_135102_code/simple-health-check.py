# Task: simple-health-check
# Pipeline status: approved
# Target file: feature.py

# feature.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}