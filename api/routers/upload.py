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

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..database import get_db

router = APIRouter()

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


@router.get("/keys/{api_key}/patient")
def resolve_api_key(api_key: str, db: Session = Depends(get_db)):
    """API Key로 매핑된 환자 ID 조회"""
    patient_id = resolve_api_key_db(api_key, db)
    if not patient_id:
        raise HTTPException(status_code=404, detail="해당 API Key를 찾을 수 없습니다")
    return {"patient_id": patient_id}


@router.get("/keys/patient/{patient_id}")
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
class PatientAssessmentInfo(BaseModel):
    patient_id: str
    request_org: Optional[str] = None
    assess_date: Optional[str] = None
    assess_person: Optional[str] = None
    edu: Optional[int] = None
    excluded: str = '0'
    post_stroke_date: Optional[str] = None
    diagnosis: Optional[str] = None
    diagnosis_etc: Optional[str] = None
    stroke_type: Optional[str] = None
    lesion_location: Optional[str] = None
    hemiplegia: Optional[str] = None
    hemineglect: Optional[str] = None
    visual_field_defect: Optional[str] = None


class FileMetadata(BaseModel):
    patient_id: str
    order_num: int
    assess_type: str
    question_cd: str
    question_no: int
    question_minor_no: int
    file_name: str
    duration: float
    rate: int
    # Path 관련 필드 제거 (MAIN_PATH, SUB_PATH)


class ScoreData(BaseModel):
    patient_id: str
    order_num: int
    assess_type: str
    question_cd: str
    question_no: int
    question_minor_no: int
    score: float


class ScoreBulk(BaseModel):
    scores: List[ScoreData]


def get_next_order_num(db: Session, patient_id: str) -> int:
    """해당 환자의 다음 order_num 반환 (기본 1)"""
    query = text("""
        SELECT IFNULL(MAX(order_num) + 1, 1)
        FROM SCORE
        WHERE PN = :patient_id
    """)
    return int(db.execute(query, {"patient_id": patient_id}).scalar() or 1)


# ============================================
# Endpoints
# ============================================

@router.get("/keys/generate")
def generate_client_key():
    """
    클라이언트에서 API 접근 시 사용할 고유 키 생성
    - UTC 타임스탬프(마이크로초) + 랜덤 6자리 영숫자 조합
    """
    return {"detail": "키 발급은 업로드 시 자동 생성됩니다."}


@router.post("/assessments/files/upload")


async def upload_files_with_metadata(
    id: str = Form(...),
    patient_id: str = Form(..., alias="pn"),
    order_num: int = Form(...),
    assess_type: str = Form(...),
    question_cd: str = Form(...),
    question_no: int = Form(...),
    question_minor_no: int = Form(...),
    score: float = Form(...),
    filename: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    파일을 blob으로 저장 (단일 파일)
    wav, m4a 등 다양한 오디오 포맷 지원

    Args:
        id: pk
        order_num: 검사 인덱스 (evaluationId)
        question_cd: 문항 코드 (episodeIndex)
        file_name: 앱에서 전달된 파일명(p_1_0.wav)
        duration: 오디오 길이
        rate: 샘플링 레이트
        creation_date: 앱에서 전달된 생성 시각
        file: 업로드 파일 (wav, m4a 등)
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
        
        query = text("""
            INSERT INTO SCORE (
                ID, PN, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO, QUESTION_MINOR_NO, FILENAME 
            ) VALUES (
                :id, :patient_id, :order_num, :assess_type, :question_cd,
                :question_no, :question_minor_no, :filename
            )
        """)
        
        db.execute(query, {
            'id': id,
            'patient_id': patient_id,
            'order_num': order_num,
            'assess_type': assess_type,
            'question_cd': question_cd,
            'question_no': question_no,
            'question_minor_no': question_minor_no,
            'score': score,
            'filename': filename,
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


@router.get("/assessments/{patient_id}/{order_num}/files")
def get_assessment_files(
    patient_id: str,
    order_num: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key_for_patient)
):
    """
    특정 검사의 파일 목록 조회 (메타데이터만, blob 제외)
    """
    try:
        query = text("""
            SELECT 
                A.PN, A.ORDER_NUM, A.ASSESS_TYPE, A.QUESTION_CD,
                A.QUESTION_NO, A.FILE_NAME, A.DURATION, A.RATE,
                LENGTH(A.FILE_CONTENT) as FILE_SIZE
            FROM score A
            WHERE A.PN = :patient_id 
              AND A.ORDER_NUM = :order_num 
            ORDER BY A.ASSESS_TYPE, A.ORDER_NUM, A.QUESTION_NO
        """)
        
        result = db.execute(query, {
            "patient_id": patient_id,
            "order_num": order_num
        }).fetchall()
        
        return [
            {
                "PATIENT_ID": row[0],
                "ORDER_NUM": row[1],
                "ASSESS_TYPE": row[2],
                "QUESTION_CD": row[3],
                "QUESTION_NO": row[4],
                "FILE_NAME": row[5],
                "DURATION": row[6],
                "RATE": row[7],
                "FILE_SIZE": row[8]
            }
            for row in result
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 목록 조회 실패: {str(e)}")


@router.get("/assessments/{patient_id}/{order_num}/files/{question_cd}/download")
def download_file(
    patient_id: str, 
    order_num: int, 
    question_cd: str,
    question_no: int,
    convert_to_wav: bool = True,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key_for_patient)
):
    """
    특정 파일을 blob에서 다운로드
    
    Args:
        patient_id: 환자 ID
        order_num: 검사 회차
        question_cd: 문항 코드
        question_no: 문항 번호
        convert_to_wav: m4a를 wav로 변환 여부 (기본: True)
    
    Returns:
        파일 바이너리 데이터 (wav 형식)
    """
    from fastapi.responses import Response
    import tempfile
    from pydub import AudioSegment
    
    try:
        query = text("""
            SELECT FILE_CONTENT, FILE_NAME
            FROM score
            WHERE PN = :patient_id
              AND ORDER_NUM = :order_num
              AND QUESTION_CD = :question_cd
              AND QUESTION_NO = :question_no
            ORDER BY QUESTION_MINOR_NO DESC, CREATE_DATE DESC
        """)
        
        result = db.execute(query, {
            "patient_id": patient_id,
            "order_num": order_num,
            "question_cd": question_cd,
            "question_no": question_no
        }).fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
        
        file_content, file_name = result
        file_ext = os.path.splitext(file_name)[1].lower()
        
        # m4a이고 변환이 필요한 경우
        if file_ext in ['.m4a', '.mp4', '.aac'] and convert_to_wav:
            # 임시 파일로 저장
            temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
            temp_input.write(file_content)
            temp_input.close()
            
            try:
                # m4a를 wav로 변환
                audio = AudioSegment.from_file(temp_input.name, format='m4a')
                audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
                
                # 임시 wav 파일 생성
                temp_output = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
                temp_output.close()
                
                audio.export(temp_output.name, format='wav')
                
                # wav 파일 읽기
                with open(temp_output.name, 'rb') as f:
                    wav_content = f.read()
                
                # 변환된 파일명
                base_name = os.path.splitext(file_name)[0]
                output_filename = f"{base_name}.wav"
                
                return Response(
                    content=wav_content,
                    media_type="audio/wav",
                    headers={
                        "Content-Disposition": f"attachment; filename={output_filename}"
                    }
                )
            finally:
                # 임시 파일 삭제
                try:
                    os.unlink(temp_input.name)
                    os.unlink(temp_output.name)
                except:
                    pass
        else:
            # wav 파일 또는 변환 불필요한 경우 그대로 반환
            media_type = "audio/wav" if file_ext == '.wav' else "audio/mp4"
            
            return Response(
                content=file_content,
                media_type=media_type,
                headers={
                    "Content-Disposition": f"attachment; filename={file_name}"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 다운로드 실패: {str(e)}")


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
        file_result = db.execute(
            text("DELETE FROM score WHERE PN = :patient_id AND ORDER_NUM = :order_num"),
            params
        )
        score_result = db.execute(
            text("DELETE FROM score WHERE PN = :patient_id AND ORDER_NUM = :order_num"),
            params
        )
        lst_result = db.execute(
            text("DELETE FROM score WHERE PN = :patient_id AND ORDER_NUM = :order_num"),
            params
        )
        db.commit()
        return {
            "success": True,
            "deleted_files": file_result.rowcount,
            "deleted_scores": score_result.rowcount,
            "deleted_assess": lst_result.rowcount
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터 롤백 실패: {str(e)}")


@router.post("/scores/bulk")
def save_scores_bulk(data: ScoreBulk, db: Session = Depends(get_db)):
    """점수 일괄 저장"""
    try:
        if not data.scores:
            raise HTTPException(status_code=400, detail="저장할 점수 정보가 없습니다")
        
        for score in data.scores:
            check_query = text("""
                SELECT COUNT(*) 
                FROM score
                WHERE PN = :patient_id
                  AND ORDER_NUM = :order_num
                  AND QUESTION_CD = :question_cd
            """)
            
            exists = db.execute(check_query, {
                "patient_id": score.patient_id,
                "order_num": score.order_num,
                "question_cd": score.question_cd
            }).scalar()
            
            if exists:
                update_query = text("""
                    UPDATE score
                    SET SCORE = :score,
                        ASSESS_TYPE = :assess_type
                    WHERE PN = :patient_id
                      AND ORDER_NUM = :order_num
                      AND QUESTION_CD = :question_cd
                """)
                db.execute(update_query, {
                    "score": score.score,
                    "assess_type": score.assess_type,
                    "patient_id": score.patient_id,
                    "order_num": score.order_num,
                    "question_cd": score.question_cd
                })
            else:
                insert_query = text("""
                    INSERT INTO score (
                        PN, ORDER_NUM, ASSESS_TYPE, QUESTION_CD,
                        QUESTION_NO, QUESTION_MINOR_NO, SCORE
                    ) VALUES (
                        :patient_id, :order_num, :assess_type, :question_cd,
                        :question_no, :question_minor_no, :score
                    )
                """)
                db.execute(insert_query, {
                    "patient_id": score.patient_id,
                    "order_num": score.order_num,
                    "assess_type": score.assess_type,
                    "question_cd": score.question_cd,
                    "question_no": score.question_no,
                    "question_minor_no": score.question_minor_no,
                    "score": score.score
                })
        
        db.commit()
        
        return {
            "success": True,
            "message": f"점수 {len(data.scores)}건 저장 완료",
            "count": len(data.scores)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"점수 저장 실패: {str(e)}")
