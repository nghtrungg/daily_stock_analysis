# -*- coding: utf-8 -*-
"""
===================================
Health-check endpoint
===================================

Provides /api/v1/health for load balancers and monitoring systems.
"""

from datetime import datetime

from fastapi import APIRouter

from api.v1.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Return service health.
    
    Intended for load balancers and monitoring systems.
    
    Returns:
        HealthResponse containing service status and timestamp.
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat()
    )
