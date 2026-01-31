from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Dict
from pydantic import BaseModel
import sys
import os
import datetime
import random
import string
import threading
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

# 현재 api key 로직: 환자 파일 업로드하면 발급, 그후 환자ID별로 저장 및 조회에 사용
def issue_api_key(patient_id: str, db: Session) -> str:
    """환자별 API Key 재사용, 없으면 발급 후 DB에 저장"""
    row = db.execute(
        text(
            "SELECT API_KEY FROM api_key WHERE PATIENT_ID = :patient_id"
        ),
        {"patient_id": patient_id}
    ).fetchone()
    if row and row[0]:
        key = row[0]
        db.execute(
            text("UPDATE api_key SET LAST_USED_AT = NOW() WHERE PATIENT_ID = :patient_id"),
            {"patient_id": patient_id}
        )
        db.commit()
        return key

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S%f")
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    key = f"{now}-{rand}"
    db.execute(
        text(
            """
            INSERT INTO api_key (PATIENT_ID, API_KEY, ISSUED_AT, LAST_USED_AT)
            VALUES (:patient_id, :api_key, NOW(), NOW())
            ON DUPLICATE KEY UPDATE API_KEY = VALUES(API_KEY), LAST_USED_AT = NOW()
            """
        ),
        {"patient_id": patient_id, "api_key": key}
    )
    db.commit()
    return key


def resolve_api_key_db(api_key: str, db: Session) -> Optional[str]:
    """API Key로 환자 ID 조회 (DB)"""
    row = db.execute(
        text(
            """
            SELECT PATIENT_ID
            FROM api_key
            WHERE API_KEY = :api_key
            """
        ),
        {"api_key": api_key}
    ).fetchone()
    if row:
        # 마지막 사용 시각 업데이트
        db.execute(
            text(
                "UPDATE api_key SET LAST_USED_AT = NOW() WHERE API_KEY = :api_key"
            ),
            {"api_key": api_key}
        )
        db.commit()
        return row[0]
    return None


def require_api_key_for_patient(
    patient_id: str,
    key: Optional[str] = Query(None),
    header_key: Optional[str] = Header(None, alias="X-API-KEY"),
    db: Session = Depends(get_db)
):
    api_key = header_key or key
    if not api_key:
        raise HTTPException(status_code=401, detail="API Key가 필요합니다")
    mapped = resolve_api_key_db(api_key, db)
    if mapped != patient_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 API Key")
    return api_key


@router.get("/keys/patient")
def resolve_api_key(api_key: str, db: Session = Depends(get_db)):
    """API Key로 매핑된 환자 ID 조회"""
    patient_id = resolve_api_key_db(api_key, db)
    if not patient_id:
        raise HTTPException(status_code=404, detail="해당 API Key를 찾을 수 없습니다")
    return {"patient_id": patient_id}


@router.get("/keys/{patient_id}")
def get_api_key_by_patient(patient_id: str, db: Session = Depends(get_db)):
    """환자 ID로 API Key 조회, 없으면 새로 발급하여 반환"""
    row = db.execute(
        text(
            """
            SELECT API_KEY
            FROM api_key
            WHERE PATIENT_ID = :patient_id
            """
        ),
        {"patient_id": patient_id}
    ).fetchone()

    if row and row[0]:
        api_key = row[0]
        db.execute(
            text("UPDATE api_key SET LAST_USED_AT = NOW() WHERE PATIENT_ID = :patient_id"),
            {"patient_id": patient_id}
        )
        db.commit()
        return {"api_key": api_key}

    # 없으면 발급
    api_key = issue_api_key(patient_id, db)
    return {"api_key": api_key}

# ============================================
# Request Models
# ============================================


def get_next_order_num(db: Session, patient_id: str) -> int:
    """해당 환자의 다음 order_num 반환 (기본 1)"""
    query = text("""
        SELECT IFNULL(MAX(ORDER_NUM) + 1, 1)
        FROM AUDIO_STORAGE
        WHERE PATIENT_ID = :patient_id
    """)
    return int(db.execute(query, {"patient_id": patient_id}).scalar() or 1)


# ============================================
# Endpoints
# ============================================

@router.post("/assessments/files/upload")
async def upload_files_with_metadata(
    patient_id: str = Form(..., alias="pn"),
    order_num: int = Form(..., alias="evaluationId"),
    assess_type: str = Form(..., alias="type"),
    question_cd: str = Form(..., alias="episode"),
    filename: str = Form(..., alias="fileName"),
    duration: float = Form(...),
    rate: str = Form(...),
    score: float = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    파일을 MEDIUMBLOB으로 저장 (단일 파일)
    wav, m4a 등 다양한 오디오 포맷 지원

    """
    name_parts = filename.split("_")
    question_no = int(name_parts[1])
    question_minor_no = int(name_parts[2].split('.')[0])

    try:
        # 업로드 시 인증 없이 키 발급
        api_key = issue_api_key(patient_id, db)

        # 파일 확장자 검증
        file_ext = os.path.splitext(filename)[1].lower()
        allowed_extensions = ['.wav', '.m4a', '.mp4', '.aac']
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 파일 형식: {file_ext}. 허용: {', '.join(allowed_extensions)}"
            )
        # 파일을 바이너리(bytes)로 읽음
        file_content = await file.read()

        # ================================= 2026-01-31 jhkim =================================
        # 동일 PK 조합 중복 시 score/file/duration만 갱신 (ON DUPLICATE KEY UPDATE)
        query = text("""
            INSERT INTO audio_storage (
                PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO, QUESTION_MINOR_NO, DURATION, SCORE, RATE, FILE
            ) VALUES (
                :patient_id, :order_num, :assess_type, :question_cd,
                :question_no, :question_minor_no, :duration, :score, :rate, :file
            )
            ON DUPLICATE KEY UPDATE
                SCORE = VALUES(SCORE),
                DURATION = VALUES(DURATION),
                RATE = VALUES(RATE),
                FILE = VALUES(FILE),
                USE_TF = 0
        """)
        # ====================================================================================
        
        db.execute(query, {
            'patient_id': patient_id,
            'order_num': order_num,
            'assess_type': assess_type,
            'question_cd': question_cd,
            'question_no': question_no,
            'question_minor_no': question_minor_no,
            'duration': duration,
            'rate': rate,
            'score': score,
            'file': file_content
        })
        db.commit()
        
        return {
            "success": True,
            "message": "파일 저장 완료",
            "api_key": api_key
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"파일 저장 실패: {str(e)}")


def _run_model_worker_once():
    try:
        from scripts.model_worker import _init_heavy_imports, process_pending_jobs
        pd, text, SessionLocal, APIClient, model_process, save_scores_to_db = _init_heavy_imports()
        process_pending_jobs(pd, text, SessionLocal, APIClient, model_process, save_scores_to_db)
    except Exception as e:
        logger.error(f"모델 워커 실행 실패: {e}")


@router.post("/assessments/run-model")
def run_model_worker():
    """
    모델 워커를 1회 실행 (비동기 스레드로 처리).
    """
    worker_thread = threading.Thread(target=_run_model_worker_once, daemon=True)
    worker_thread.start()
    return {"success": True, "message": "모델 워커 실행 요청됨"}

#  {
#     "detail":[
#         {
#             "type":"missing",
#             "loc":[
#                 "body","scores",0,"patient_id"
#                 ],
#                 "msg":"Field required",
#                 "input":{
#                     "assess_type":"CLAP_D",
#                     "filename":"p_1_1.wav",
#                     "id":1,
#                     "order_num":1,
#                     "pn":"1001",
#                     "question_cd":"AH_SOUND",
#                     "question_no":67,
#                     "score":2.0    
#                 }
#                 },{
#                     "type":"missing",
#                     "loc":[
#                         "body","scores",0,"question_minor_no"
#                         ],
#                     "msg":"Field required",
#                     "input":{
#                         "assess_type":"CLAP_D","filename":"p_1_1.wav","id":1,"order_num":1,"pn":"1001","question_cd":"AH_SOUND","question_no":67,"score":2.0}},{"type":"missing","loc":["body","scores",1,"patient_id"],"msg":"Field required","input":{"assess_type":"CLAP_D","filename":"p_1_1.wav","id":2,"order_num":1,"pn":"1001","question_cd":"AH_SOUND","question_no":67,"score":2.0}},{"type":"missing","loc":["body","scores",1,"question_minor_no"],"msg":"Field required","input":{"assess_type":"CLAP_D","filename":"p_1_1.wav","id":2,"order_num":1,"pn":"1001","question_cd":"AH_SOUND","question_no":67,"score":2.0}}]}


@router.get("/assessments/status/{patient_id}/{order_num}")
def check_modeling_status(
    patient_id: str,
    order_num: int,
    db: Session = Depends(get_db),
):
    """
    해당 환자/회차의 모델링 상태 확인.
    - has_data: AUDIO_STORAGE에 데이터가 존재하는지
    - is_processing: 업로드됐지만 모델링 미완료(USE_TF=0) 데이터가 있는지
    - is_complete: 모델링 완료(USE_TF=1) 데이터가 있는지
    """
    row = db.execute(
        text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN USE_TF = 0 THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN USE_TF = 1 THEN 1 ELSE 0 END) as completed
            FROM AUDIO_STORAGE
            WHERE PATIENT_ID = :patient_id AND ORDER_NUM = :order_num
        """),
        {"patient_id": patient_id, "order_num": order_num}
    ).fetchone()

    total = row[0] if row else 0
    pending = row[1] if row else 0
    completed = row[2] if row else 0

    return {
        "has_data": total > 0,
        "is_processing": pending > 0 and total > 0,
        "is_complete": completed > 0 and pending == 0,
    }


@router.post("/assessments/files/bulk-upload")
async def upload_files_bulk(
    pn: str = Form(...),
    evaluationId: str = Form(...),
    audioFiles: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """
    여러 파일을 한 번에 업로드하여 BLOB으로 저장
    """
    try:
        # API Key 발급
        api_key = issue_api_key(pn, db)
        
        uploaded_count = 0
        for file in audioFiles:
            # 파일을 바이너리(bytes)로 읽음
            file_content = await file.read()
            
            # 파일 확장자 검증
            file_ext = os.path.splitext(file.filename)[1].lower()
            allowed_extensions = ['.wav', '.m4a', '.mp4', '.aac']
            
            if file_ext not in allowed_extensions:
                continue  # 지원하지 않는 파일 형식은 건너뛰기
            
            # SQLAlchemy text()를 사용하여 쿼리 실행
            query = text("""
                INSERT INTO audio_storage (pn, order_num, filename, audio_blob)
                VALUES (:pn, :order_num, :filename, :audio_blob)
            """)
            
            db.execute(query, {
                'pn': pn,
                'order_num': evaluationId,
                'filename': file.filename,
                'audio_blob': file_content
            })
            uploaded_count += 1

        db.commit()
        return {
            "success": True,
            "message": f"{uploaded_count}개 파일 DB 저장 완료",
            "api_key": api_key
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"파일 저장 실패: {str(e)}")

from pydantic import BaseModel
from typing import List, Optional

class ScoreIn(BaseModel):
    patient_id: str
    order_num: int
    assess_type: str
    question_cd: str
    question_no: int
    question_minor_no: int
    score: Optional[float] = None

class ScoresBulkIn(BaseModel):
    scores: List[ScoreIn]

@router.post("/assessments/score")
def save_scores_bulk(
    payload: ScoresBulkIn,
    db: Session = Depends(get_db),
):
    """
    모델 결과 점수들을 AUDIO_STORAGE 테이블에 직접 업데이트하는 엔드포인트.
    클라이언트에서 json={"scores": [...]} 형태로 호출.
    """
    try:
        for item in payload.scores:
            query = text("""
                UPDATE AUDIO_STORAGE
                SET SCORE = :score,
                    USE_TF = 1
                WHERE PATIENT_ID = :patient_id
                  AND ORDER_NUM = :order_num
                  AND ASSESS_TYPE = :assess_type
                  AND QUESTION_CD = :question_cd
                  AND QUESTION_NO = :question_no
                  AND QUESTION_MINOR_NO = :question_minor_no
            """)
            db.execute(query, {
                "patient_id": item.patient_id,
                "order_num": item.order_num,
                "assess_type": item.assess_type,
                "question_cd": item.question_cd,
                "question_no": item.question_no,
                "question_minor_no": item.question_minor_no,
                "score": item.score,
            })

        db.commit()
        return {"success": True, "count": len(payload.scores)}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"점수 저장 실패: {str(e)}")

@router.delete("/assessments/{patient_id}/{order_num}")
def delete_assessment(
    patient_id: str,
    order_num: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key_for_patient)
):
    """업로드 실패 시 해당 환자/회차 데이터 롤백용"""
    try:
        params = {"patient_id": patient_id, "order_num": order_num}
        result = db.execute(
            text("DELETE FROM AUDIO_STORAGE WHERE PATIENT_ID = :patient_id AND ORDER_NUM = :order_num"),
            params
        )
        db.commit()
        return {
            "success": True,
            "deleted_rows": result.rowcount
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터 롤백 실패: {str(e)}")
