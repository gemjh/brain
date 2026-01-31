import importlib.util
import subprocess
import sys
from pathlib import Path
from contextlib import asynccontextmanager

def _ensure_api_requirements():
    req_path = Path(__file__).resolve().parent / "environment.yaml"
    marker_path = Path(__file__).resolve().parent / ".api_env_installed"

    if not req_path.exists() or marker_path.exists():
        return

    has_fastapi = importlib.util.find_spec("fastapi") is not None
    has_uvicorn = importlib.util.find_spec("uvicorn") is not None
    if has_fastapi and has_uvicorn:
        marker_path.write_text("ok")
        return

    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_path)])
    marker_path.write_text("ok")

try:
    from fastapi import FastAPI, Response
    from fastapi.middleware.cors import CORSMiddleware
except ModuleNotFoundError:
    _ensure_api_requirements()
    from fastapi import FastAPI, Response
    from fastapi.middleware.cors import CORSMiddleware
# ================================= 2026-01-31 jhkim =================================
import threading
import logging
# ====================================================================================

from . import models
from .database import get_db
from .routers import reports, upload

# ================================= 2026-01-31 jhkim =================================
logger = logging.getLogger(__name__)

def _start_model_worker():
    """model_worker를 백그라운드 데몬 스레드로 실행 (5분 주기 폴링)"""
    try:
        import sys
        import os
        from pathlib import Path
        ROOT = Path(__file__).resolve().parents[1]
        sys.path.append(str(ROOT / "ui"))
        sys.path.append(str(ROOT))

        from scripts.model_worker import _init_heavy_imports, process_pending_jobs
        import time

        pd, text, SessionLocal, APIClient, model_process, save_scores_to_db = _init_heavy_imports()
        logger.info("모델 워커 백그라운드 스레드 시작 (주기: 300초)")

        while True:
            try:
                process_pending_jobs(pd, text, SessionLocal, APIClient, model_process, save_scores_to_db)
            except Exception as e:
                logger.error(f"모델 워커 처리 중 오류: {e}")
            time.sleep(300)
    except Exception as e:
        logger.error(f"모델 워커 초기화 실패: {e}")
# ====================================================================================


# ============================================
# Lifespan 이벤트 (startup/shutdown 대체)
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # Startup
    print("=" * 50)
    print("CLAP API Server Starting...")
    print("=" * 50)
    print("✅ Routers registered:")
    for route in app.routes:
        if hasattr(route, "methods"):
            print(f"  {list(route.methods)[0]:6s} {route.path}")
    print("=" * 50)

    # ================================= 2026-01-31 jhkim =================================
    # model_worker 백그라운드 데몬 스레드 시작 (5분 주기)
    worker_thread = threading.Thread(target=_start_model_worker, daemon=True)
    worker_thread.start()
    print("✅ Model worker 백그라운드 스레드 시작됨 (300초 주기)")
    # ====================================================================================

    yield  # 애플리케이션 실행


# ============================================
# FastAPI 앱 생성
# ============================================
app = FastAPI(
    title="CLAP API",
    version="1.0.0",
    description="CLAP 검사 시스템 API",
    lifespan=lifespan
)

# CORS 설정 (Streamlit에서 접근 가능하도록)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 구체적인 도메인 지정 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# 라우터 등록
# ============================================
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(upload.router, prefix="/api/v1", tags=["Upload & Scores"])


# ============================================
# main
# ============================================
@app.get("/")
def read_root():
    """API 루트 엔드포인트"""
    return {
        "message": "CLAP API Server",
        "version": "1.0.0",
        "status": "running"
    }
