import os

import uvicorn


def run():
    """uvicorn 실행 헬퍼 (Kotlin 클라이언트용 경량 엔트리포인트)"""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("UVICORN_RELOAD", "false").lower() == "true"

    uvicorn.run("api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run()
