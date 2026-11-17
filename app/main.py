import csv
import io
from decimal import Decimal, InvalidOperation
from pathlib import Path
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from .auth import create_access_token, get_current_user, verify_demo_credentials
from .config import get_settings
from .reconciler import reconcile
from .security import SecurityAndObservabilityMiddleware, SlidingWindowLimiter, safe_api_exception_handler

BASE, DATA = Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent / "data"
settings = get_settings(); MAX_UPLOAD_BYTES = settings.max_upload_mb * 1024 * 1024
PLATFORM_COLUMNS = {"transaction_id", "timestamp_utc", "type", "parent_transaction_id", "net_amount_exact"}
BANK_COLUMNS = {"settlement_id", "transaction_id", "settlement_date_utc", "type", "parent_transaction_id", "settled_amount"}
IDENTIFIER_COLUMNS = {"transaction_id", "customer_id", "settlement_id", "parent_transaction_id"}
NUMERIC_COLUMNS = {"gross_amount", "platform_fee_exact", "net_amount_exact", "bank_fee_rounded", "settled_amount"}
app = FastAPI(title="Month-End Reconciliation")
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "HX-Request"])
app.add_middleware(SecurityAndObservabilityMiddleware)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
app.state.rate_limiter = SlidingWindowLimiter(); app.state.reset_rate_limits = app.state.rate_limiter.reset
_cached_result = None

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path, ip = request.url.path, (request.client.host if request.client else "unknown")
    if path == "/auth/login" and not app.state.rate_limiter.allow(f"login:{ip}", 10): return JSONResponse({"detail":"Too many login attempts. Try again in a minute."}, 429)
    if path.startswith("/api/") and not app.state.rate_limiter.allow(f"api:{ip}", 120): return JSONResponse({"detail":"Rate limit exceeded. Try again in a minute."}, 429)
    return await call_next(request)

@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    if request.url.path.startswith("/api/"): return await safe_api_exception_handler(request, exc)
    raise exc
@app.exception_handler(HTTPException)
async def http_exception(request: Request, exc: HTTPException):
    headers = {"HX-Redirect":"/login"} if exc.status_code == 401 and request.headers.get("HX-Request") == "true" else {}
    return JSONResponse({"detail":exc.detail}, exc.status_code, headers=headers)

def sanitize_identifier(value: str) -> str: return "'" + value if value and value[0] in {"=", "+", "-", "@", "\t", "\r"} else value
def parse_csv(payload: bytes, required: set[str], source: str) -> list[dict[str, str]]:
    if len(payload) > MAX_UPLOAD_BYTES: raise ValueError(f"{source} CSV exceeds the {settings.max_upload_mb}MB limit.")
    try:
        reader = csv.DictReader(io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8-sig", newline="")); missing = required - set(reader.fieldnames or [])
        if missing: raise ValueError(f"{source} CSV is missing required columns: {', '.join(sorted(missing))}.")
        rows = []
        for number, row in enumerate(reader, 2):
            if len(rows) >= settings.max_csv_rows: raise ValueError(f"{source} CSV exceeds the {settings.max_csv_rows:,} row limit.")
            for key in IDENTIFIER_COLUMNS & row.keys(): row[key] = sanitize_identifier(row.get(key) or "")
            for key in NUMERIC_COLUMNS & row.keys():
                if row.get(key) not in (None, ""):
                    try: Decimal(row[key])
                    except InvalidOperation as exc: raise ValueError(f"{source} CSV row {number} has invalid numeric value in {key}.") from exc
            rows.append(row)
        return rows
    except UnicodeDecodeError as exc: raise ValueError(f"{source} CSV must be UTF-8 encoded.") from exc
def default_rows(): return parse_csv((DATA / "platform_ledger.csv").read_bytes(), PLATFORM_COLUMNS, "Platform"), parse_csv((DATA / "bank_settlements.csv").read_bytes(), BANK_COLUMNS, "Bank")
def build_context(request, platform, bank):
    global _cached_result; _cached_result = reconcile(platform, bank); return {"request":request, "result":_cached_result, "categories":_cached_result.by_category()}
def alert(request, text, status_code=400): return render(request, "partials/error.html", {"error":text}, status_code)

def render(request: Request, name: str, context: dict, status_code: int = 200): return templates.TemplateResponse(request, name, context, status_code=status_code)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request): return render(request, "login.html", {"email":settings.demo_user_email,"password":settings.demo_user_password})
@app.post("/auth/login")
async def login(request: Request):
    content_type = request.headers.get("content-type", "")
    is_json = "application/json" in content_type
    try: data = await request.json() if is_json else await request.form()
    except Exception: data = {}
    if not verify_demo_credentials(str(data.get("email", "")), str(data.get("password", ""))): raise HTTPException(401, "Invalid email or password")
    token = create_access_token(settings.demo_user_email)
    if request.headers.get("HX-Request") == "true":
        response = Response(status_code=200, headers={"HX-Redirect":"/"})
    elif is_json:
        response = JSONResponse({"access_token":token,"token_type":"bearer"})
    else:
        # Normal browser form submission: set the cookie then navigate to the dashboard.
        response = RedirectResponse("/", status_code=303)
    response.set_cookie("access_token", token, httponly=True, samesite="lax", secure=settings.environment == "production", max_age=settings.access_token_expire_minutes*60); return response
@app.post("/auth/logout")
async def logout():
    response = RedirectResponse("/login", 303); response.delete_cookie("access_token"); return response
@app.get("/auth/me")
async def me(user: dict = Depends(get_current_user)): return {"sub":user["sub"],"role":user["role"]}

async def browser_user(request: Request):
    try: return await get_current_user(request)
    except HTTPException: return None
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not await browser_user(request): return RedirectResponse("/login", 302)
    platform, bank = default_rows(); return render(request, "index.html", build_context(request, platform, bank))
@app.post("/api/reconcile/default", response_class=HTMLResponse)
async def reconcile_default(request: Request, _: dict = Depends(get_current_user)):
    platform, bank = default_rows(); return render(request, "partials/results.html", build_context(request, platform, bank))
@app.post("/api/reconcile/upload", response_class=HTMLResponse)
async def reconcile_upload(request: Request, platform_file: UploadFile = File(...), bank_file: UploadFile = File(...), _: dict = Depends(get_current_user)):
    if not (platform_file.filename or "").lower().endswith(".csv") or not (bank_file.filename or "").lower().endswith(".csv"): return alert(request, "Both uploads must be .csv files.")
    try: platform = parse_csv(await platform_file.read(MAX_UPLOAD_BYTES+1), PLATFORM_COLUMNS, "Platform"); bank = parse_csv(await bank_file.read(MAX_UPLOAD_BYTES+1), BANK_COLUMNS, "Bank")
    except ValueError as exc: return alert(request, str(exc), 413 if "MB limit" in str(exc) else 400)
    return render(request, "partials/results.html", build_context(request, platform, bank))
@app.get("/api/gaps/filter", response_class=HTMLResponse)
async def filter_gaps(request: Request, gap_type: str = Query("ALL"), q: str = Query(""), _: dict = Depends(get_current_user)):
    global _cached_result
    if _cached_result is None: platform, bank = default_rows(); build_context(request, platform, bank)
    wanted, search = gap_type.upper(), q.strip().lower(); groups = {"DUPLICATES":{"DUPLICATE_PLATFORM","DUPLICATE_BANK"}, "MISSING_MISMATCH":{"MISSING_IN_BANK","AMOUNT_MISMATCH"}}
    gaps = [d for d in _cached_result.discrepancies if (wanted == "ALL" or d.gap_type in groups.get(wanted,{wanted})) and (not search or search in d.transaction_id.lower())]
    return render(request, "partials/table.html", {"result":_cached_result,"discrepancies":gaps,"table_rows_only":True})
@app.get("/health")
async def health(): return JSONResponse({"status":"ok"})
@app.get("/favicon.ico", status_code=204)
async def favicon(): return Response(status_code=204)
@app.get("/hybridaction/{path:path}", status_code=204)
async def hybridaction(path: str): return Response(status_code=204)
