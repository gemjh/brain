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

# 간단한 API Key 저장소 (프로세스 메모리): key -> patient_id
valid_api_keys: Dict[str, str] = {}


def issue_api_key(patient_id: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S%f")
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    key = f"{now}-{rand}"
    valid_api_keys[key] = patient_id
    return key


def require_api_key_for_patient(
    patient_id: str,
    key: Optional[str] = Query(None),
    header_key: Optional[str] = Header(None, alias="X-API-KEY")
):
    api_key = header_key or key
    if not api_key:
        raise HTTPException(status_code=401, detail="API Key가 필요합니다")
    mapped = valid_api_keys.get(api_key)
    if mapped != patient_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 API Key")
    return api_key


@router.get("/keys/{api_key}/patient")
def resolve_api_key(api_key: str):
    """API Key로 매핑된 환자 ID 조회"""
    patient_id = valid_api_keys.get(api_key)
    if not patient_id:
        raise HTTPException(status_code=404, detail="해당 API Key를 찾을 수 없습니다")
    return {"patient_id": patient_id}

# ============================================
# Request Models
# ============================================
class PatientAssessmentInfo(BaseModel):
    patient_id: str
    order_num: int
    request_org: Optional[str] = None
    assess_date: Optional[str] = None
    assess_person: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
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

@router.get("/patients/{patient_id}/order")
def get_order_num(
    patient_id: str,
    db: Session = Depends(get_db),
):
    """환자의 수행회차 조회"""
    try:
        query = text("""
            SELECT IFNULL(MAX(order_num) + 1, 1) 
            FROM assess_lst 
            WHERE PATIENT_ID = :patient_id
        """)
        result = db.execute(query, {"patient_id": patient_id}).fetchone()
        return {"order_num": result[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수행회차 조회 실패: {str(e)}")


@router.post("/assessments/patient-info")
def save_patient_assessment(
    data: PatientAssessmentInfo,
    db: Session = Depends(get_db),
    api_key: Optional[str] = Depends(
        lambda: None  # patient-info 저장은 키가 없어도 진행 (초기 업로드)
    )
):
    """환자 검사 정보 저장"""
    try:
        params = {
            'patient_id': data.patient_id,
            'order_num': data.order_num,
            'request_org': data.request_org,
            'assess_date': data.assess_date,
            'assess_person': data.assess_person,
            'age': data.age,
            'edu': data.edu,
            'excluded': data.excluded,
            'post_stroke_date': data.post_stroke_date,
            'diagnosis': data.diagnosis,
            'diagnosis_etc': data.diagnosis_etc,
            'stroke_type': data.stroke_type,
            'lesion_location': data.lesion_location,
            'hemiplegia': data.hemiplegia,
            'hemineglect': data.hemineglect,
            'visual_field_defect': data.visual_field_defect,
        }
        
        query = text("""
            INSERT INTO assess_lst (
                PATIENT_ID, ORDER_NUM, REQUEST_ORG, ASSESS_DATE, ASSESS_PERSON,
                AGE, EDU, EXCLUDED, POST_STROKE_DATE, DIAGNOSIS, DIAGNOSIS_ETC,
                STROKE_TYPE, LESION_LOCATION, HEMIPLEGIA, HEMINEGLECT, VISUAL_FIELD_DEFECT
            ) VALUES (
                :patient_id, :order_num, :request_org, :assess_date, :assess_person,
                :age, :edu, :excluded, :post_stroke_date, :diagnosis, :diagnosis_etc,
                :stroke_type, :lesion_location, :hemiplegia, :hemineglect, :visual_field_defect
            )
        """)
        
        db.execute(query, params)
        db.commit()
        
        return {
            "success": True,
            "message": f"환자 검사 정보 저장 완료: {data.patient_id}",
            "patient_id": data.patient_id,
            "order_num": data.order_num,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"환자 검사 정보 저장 실패: {str(e)}")


@router.post("/assessments/files/upload")
async def upload_files_with_metadata(
    patient_id: str,
    order_num: int,
    assess_type: str,
    question_cd: str,
    question_no: int,
    question_minor_no: int,
    duration: float,
    rate: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    파일을 blob으로 저장 (단일 파일)
    wav, m4a 등 다양한 오디오 포맷 지원
    
    Args:
        patient_id: 환자 ID
        order_num: 검사 회차
        assess_type: 검사 유형 (CLAP_A, CLAP_D)
        question_cd: 문항 코드
        question_no: 문항 번호
        question_minor_no: 하위 문항 번호
        duration: 오디오 길이
        rate: 샘플링 레이트
        file: 업로드 파일 (wav, m4a 등)
    """
    try:
        # 업로드 시에는 인증 요구하지 않고 키를 새로 발급
        api_key = issue_api_key(patient_id)

        # 파일 읽기
        file_content = await file.read()
        
        # 파일 확장자 검증
        file_ext = os.path.splitext(file.filename)[1].lower()
        allowed_extensions = ['.wav', '.m4a', '.mp4', '.aac']
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 파일 형식: {file_ext}. 허용: {', '.join(allowed_extensions)}"
            )
        
        query = text("""
            INSERT INTO assess_file_lst (
                PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, 
                QUESTION_NO, QUESTION_MINOR_NO, FILE_NAME, 
                DURATION, RATE, FILE_CONTENT
            ) VALUES (
                :patient_id, :order_num, :assess_type, :question_cd,
                :question_no, :question_minor_no, :file_name,
                :duration, :rate, :file_content
            )
        """)
        
        db.execute(query, {
            'patient_id': patient_id,
            'order_num': order_num,
            'assess_type': assess_type,
            'question_cd': question_cd,
            'question_no': question_no,
            'question_minor_no': question_minor_no,
            'file_name': file.filename,
            'duration': duration,
            'rate': rate,
            'file_content': file_content
        })
        db.commit()
        
        return {
            "success": True,
            "message": f"파일 저장 완료: {file.filename}",
            "file_size": len(file_content),
            "file_type": file_ext,
            "api_key": api_key
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"파일 저장 실패: {str(e)}")


@router.post("/assessments/files/bulk-upload")
async def upload_files_bulk(
    files: List[UploadFile] = File(...),
    metadata: str = None,  # JSON 문자열로 메타데이터 전달
    db: Session = Depends(get_db),
):
    """
    여러 파일을 한번에 blob으로 저장
    
    Args:
        files: 업로드 파일 리스트
        metadata: 파일별 메타데이터 (JSON 문자열)
    """
    import json
    
    try:
        # 메타데이터 파싱
        metadata_list = json.loads(metadata) if metadata else []
        
        if len(files) != len(metadata_list):
            raise HTTPException(
                status_code=400, 
                detail="파일 개수와 메타데이터 개수가 일치하지 않습니다"
            )
        
        api_key: Optional[str] = None
        saved_files = []
        
        for file, meta in zip(files, metadata_list):
            # 업로드 시 인증 요구하지 않음, 첫 파일 기준으로 키 발급
            patient_id = meta['patient_id']
            if api_key is None:
                api_key = issue_api_key(patient_id)

            file_content = await file.read()
            
            query = text("""
                INSERT INTO assess_file_lst (
                    PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, 
                    QUESTION_NO, QUESTION_MINOR_NO, FILE_NAME, 
                    DURATION, RATE, FILE_CONTENT
                ) VALUES (
                    :patient_id, :order_num, :assess_type, :question_cd,
                    :question_no, :question_minor_no, :file_name,
                    :duration, :rate, :file_content
                )
            """)
            
            db.execute(query, {
                'patient_id': meta['patient_id'],
                'order_num': meta['order_num'],
                'assess_type': meta['assess_type'],
                'question_cd': meta['question_cd'],
                'question_no': meta['question_no'],
                'question_minor_no': meta['question_minor_no'],
                'file_name': file.filename,
                'duration': meta['duration'],
                'rate': meta['rate'],
                'file_content': file_content
            })
            
            saved_files.append({
                'filename': file.filename,
                'size': len(file_content)
            })
        
        db.commit()
        
        return {
            "success": True,
            "message": f"{len(saved_files)}개 파일 저장 완료",
            "files": saved_files,
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
                A.PATIENT_ID, A.ORDER_NUM, A.ASSESS_TYPE, A.QUESTION_CD,
                A.QUESTION_NO, A.FILE_NAME, A.DURATION, A.RATE,
                LENGTH(A.FILE_CONTENT) as FILE_SIZE
            FROM assess_file_lst A
            INNER JOIN code_mast C 
              ON C.CODE_TYPE = 'ASSESS_TYPE' 
             AND A.ASSESS_TYPE = C.MAST_CD 
             AND A.QUESTION_CD = C.SUB_CD
            WHERE A.PATIENT_ID = :patient_id 
              AND A.ORDER_NUM = :order_num 
              AND A.USE_YN = 'Y'
            ORDER BY A.ASSESS_TYPE, C.ORDER_NUM, A.QUESTION_NO
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
        # 같은 question_cd 파일이 여러 개 있으면 minor_no이 가장 큰 한 파일만 가져옴
        query = text("""
            SELECT FILE_CONTENT, FILE_NAME
            FROM assess_file_lst
            WHERE PATIENT_ID = :patient_id
              AND ORDER_NUM = :order_num
              AND QUESTION_CD = :question_cd
              AND QUESTION_NO = :question_no
              AND USE_YN = 'Y'
            ORDER BY QUESTION_MINOR_NO DESC, CREATE_DATE DESC
            LIMIT 1
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


@router.post("/assessments/{patient_id}/{order_num}/deduplicate")
def handle_duplicate_files(
    patient_id: str,
    order_num: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key_for_patient)
):
    """중복 파일 처리 - QUESTION_MINOR_NO가 작은 것을 USE_YN='N'으로 설정"""
    try:
        check_query = text("""
            SELECT PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO, COUNT(*) as cnt
            FROM assess_file_lst
            WHERE PATIENT_ID = :patient_id 
              AND ORDER_NUM = :order_num 
              AND USE_YN = 'Y'
            GROUP BY PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO
            HAVING COUNT(*) >= 2
        """)
        
        duplicates = db.execute(check_query, {
            "patient_id": patient_id,
            "order_num": order_num
        }).fetchall()
        
        if not duplicates:
            return {
                "success": True,
                "message": "중복 파일 없음",
                "deactivated_count": 0
            }
        
        update_query = text("""
            WITH ranked_records AS (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO
                        ORDER BY QUESTION_MINOR_NO ASC, CREATE_DATE ASC
                    ) AS rn
                FROM assess_file_lst
                WHERE PATIENT_ID = :patient_id 
                  AND ORDER_NUM = :order_num 
                  AND USE_YN = 'Y'
                  AND (PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO) IN (
                    SELECT PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO
                    FROM assess_file_lst
                    WHERE PATIENT_ID = :patient_id 
                      AND ORDER_NUM = :order_num 
                      AND USE_YN = 'Y'
                    GROUP BY PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO
                    HAVING COUNT(*) >= 2
                )
            )
            UPDATE assess_file_lst AS a
            JOIN ranked_records AS r
              ON a.PATIENT_ID = r.PATIENT_ID
             AND a.ORDER_NUM = r.ORDER_NUM
             AND a.ASSESS_TYPE = r.ASSESS_TYPE
             AND a.QUESTION_CD = r.QUESTION_CD
             AND a.QUESTION_NO = r.QUESTION_NO
             AND a.QUESTION_MINOR_NO = r.QUESTION_MINOR_NO
            SET a.USE_YN = 'N'
            WHERE r.rn = 1
        """)
        
        result = db.execute(update_query, {
            "patient_id": patient_id,
            "order_num": order_num
        })
        db.commit()
        
        return {
            "success": True,
            "message": f"중복 파일 {len(duplicates)}건 처리 완료",
            "duplicate_groups": len(duplicates),
            "deactivated_count": result.rowcount
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"중복 파일 처리 실패: {str(e)}")


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
            text("DELETE FROM assess_file_lst WHERE PATIENT_ID = :patient_id AND ORDER_NUM = :order_num"),
            params
        )
        score_result = db.execute(
            text("DELETE FROM assess_score_t WHERE PATIENT_ID = :patient_id AND ORDER_NUM = :order_num"),
            params
        )
        lst_result = db.execute(
            text("DELETE FROM assess_lst WHERE PATIENT_ID = :patient_id AND ORDER_NUM = :order_num"),
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


@router.post("/assessments/{patient_id}/{order_num}/init-scores")
def initialize_scores(
    patient_id: str,
    order_num: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key_for_patient)
):
    """점수 테이블 초기화"""
    try:
        query = text("""
            INSERT INTO assess_score (
                PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, 
                QUESTION_NO, QUESTION_MINOR_NO, USE_YN
            )
            SELECT 
                PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD,
                QUESTION_NO, QUESTION_MINOR_NO, USE_YN
            FROM assess_file_lst
            WHERE PATIENT_ID = :patient_id 
              AND ORDER_NUM = :order_num
        """)
        
        result = db.execute(query, {
            "patient_id": patient_id,
            "order_num": order_num
        })
        db.commit()
        
        return {
            "success": True,
            "message": f"점수 테이블 초기화 완료: {result.rowcount}건",
            "initialized_count": result.rowcount
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"점수 테이블 초기화 실패: {str(e)}")


@router.post("/scores/bulk")
def save_scores_bulk(data: ScoreBulk, db: Session = Depends(get_db)):
    """점수 일괄 저장"""
    try:
        if not data.scores:
            raise HTTPException(status_code=400, detail="저장할 점수 정보가 없습니다")
        
        for score in data.scores:
            check_query = text("""
                SELECT COUNT(*) 
                FROM assess_score
                WHERE PATIENT_ID = :patient_id
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
                    UPDATE assess_score
                    SET SCORE = :score,
                        ASSESS_TYPE = :assess_type
                    WHERE PATIENT_ID = :patient_id
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
                    INSERT INTO assess_score (
                        PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD,
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
