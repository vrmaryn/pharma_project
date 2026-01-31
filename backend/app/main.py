from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import router as api_router
from app.core.database import get_supabase_client
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Supabase FastAPI API with Chatbot Integration")

# === CORRECT PATHS ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # backend/app
DIST_DIR = os.path.join(BASE_DIR, "dist")               # backend/app/dist
DIST_DIR = os.path.abspath(DIST_DIR)

print("📁 BASE_DIR =", BASE_DIR)
print("📁 DIST_DIR =", DIST_DIR)
print("📄 index exists? ->", os.path.exists(os.path.join(DIST_DIR, "index.html")))

# === CORS ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === API ROUTES MUST COME FIRST ===
app.include_router(api_router, prefix="/api")

# === ROOT SERVE ===
@app.get("/")
async def root():
    return FileResponse(os.path.join(DIST_DIR, "index.html"))

# === STATIC FILES (REACT BUILD) — MUST COME AFTER API ROUTES ===
app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="static")

# === SPA FALLBACK (CLIENT ROUTES) ===
@app.get("/{full_path:path}")
async def spa_handler(full_path: str):
    requested = os.path.join(DIST_DIR, full_path)
    if os.path.exists(requested) and os.path.isfile(requested):
        return FileResponse(requested)
    return FileResponse(os.path.join(DIST_DIR, "index.html"))

# === SUPABASE STARTUP ===
@app.on_event("startup")
def verify_supabase():
    try:
        get_supabase_client()
        print("✅ Supabase client initialized successfully.")
    except Exception as e:
        print(f"⚠️ Failed to initialize Supabase client: {e}")
