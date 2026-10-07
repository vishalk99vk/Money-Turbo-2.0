from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services import diagnostics

router = APIRouter()


@router.get(
    "/ping",
    tags=["Health Check"],
    description="检查服务可用性",
    response_description="pong",
)
def ping(request: Request) -> str:
    return "pong"


@router.get(
    "/health",
    tags=["Health Check"],
    description=(
        "Readiness probe for load balancers and Docker. Returns only per-check "
        "status values (no paths or configuration). HTTP 503 when a check fails."
    ),
)
def health(request: Request):
    report = diagnostics.coarse_report(diagnostics.run_diagnostics())
    status_code = 503 if report["status"] == diagnostics.FAIL else 200
    return JSONResponse(report, status_code=status_code)
