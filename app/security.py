"""HTTP security, request tracing, and process-local sliding-window limits."""
import logging
import time
import uuid
from collections import defaultdict, deque
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from .config import get_settings

logger = logging.getLogger("ledgerbridge")
settings = get_settings()

class SlidingWindowLimiter:
    def __init__(self): self.events: dict[str, deque[float]] = defaultdict(deque)
    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now, bucket = time.monotonic(), self.events[key]
        while bucket and bucket[0] <= now - window: bucket.popleft()
        if len(bucket) >= limit: return False
        bucket.append(now); return True
    def reset(self): self.events.clear()

class SecurityAndObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started, request_id = time.perf_counter(), str(uuid.uuid4())
        response = await call_next(request)
        elapsed = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed:.2f}"
        response.headers.update({"X-Content-Type-Options":"nosniff", "X-Frame-Options":"DENY", "Referrer-Policy":"strict-origin-when-cross-origin", "Permissions-Policy":"camera=(), microphone=(), geolocation=()", "Content-Security-Policy":"default-src 'self'; script-src 'self' 'unsafe-inline' https://unpkg.com; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self';"})
        if settings.environment == "production": response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        logger.info("request_id=%s method=%s path=%s status_code=%s duration_ms=%.2f", request_id, request.method, request.url.path, response.status_code, elapsed)
        return response

async def safe_api_exception_handler(request: Request, exc: Exception):
    # Deliberately omit exception detail; browser HTMX calls receive a safe fragment.
    if request.headers.get("HX-Request") == "true":
        from starlette.responses import HTMLResponse
        return HTMLResponse('<div class="error-alert" role="alert">Unable to process this request safely.</div>', status_code=500)
    return JSONResponse({"detail":"Internal server error"}, status_code=500)
