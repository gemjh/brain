from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..database import get_db
from ..models import AssessmentResult

router = APIRouter()

@router.get("/{patient_id}/pending-count")
def get_pending_file_count(
    patient_id: str,
    db: Session = Depends(get_db)
):
    """
    모델링이 진행되지 않은 파일(점수 미존재) 개수 조회
    USE_YN='Y'인 파일 중 assess_score에 대응되지 않은 건을 센다.
    """
    try:
        query = text("""
            SELECT COUNT(*) AS pending_count
            FROM assess_file_lst f
            LEFT JOIN assess_score s
              ON s.PATIENT_ID = f.PATIENT_ID
             AND s.ORDER_NUM = (SELECT MAX(ORDER_NUM) FROM assess_score WHERE PATIENT_ID = :patient_id)
             AND s.QUESTION_CD = f.QUESTION_CD
             AND s.QUESTION_NO = f.QUESTION_NO
             AND s.QUESTION_MINOR_NO = f.QUESTION_MINOR_NO
            WHERE f.USE_YN = 'Y'
              AND f.PATIENT_ID = :patient_id
              AND s.PATIENT_ID IS NULL
        """)
        count = db.execute(query, {"patient_id": patient_id}).scalar() or 0
        return {"pending_count": int(count)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"미진행 파일 조회 실패: {str(e)}")


@router.get("/{patient_id}/scores", response_model=List[AssessmentResult])
def get_assessment_scores(
    patient_id: str,
    api_key: str = Header(..., alias="X-API-KEY"),
    assess_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """최신 검사의 점수 조회"""
    try:
        api_check_query = text("""
            SELECT API_KEY
            FROM api_key
            WHERE API_KEY = :api_key
        """)
        api_check_cursor = db.execute(
            api_check_query, 
            {"api_key": api_key}
        )
        api_check_info = api_check_cursor.mappings().fetchone()
        if not api_check_info:
            raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")

        query = """
            SELECT 
                s.PATIENT_ID,
                s.ORDER_NUM,
                s.ASSESS_TYPE, 
                s.QUESTION_CD,
                s.SCORE
            FROM assess_score s
            WHERE s.PATIENT_ID = :patient_id 
            AND s.ORDER_NUM = (SELECT MAX(ORDER_NUM) FROM assess_score WHERE PATIENT_ID = :patient_id)
        """
        
        params = {"patient_id": patient_id}
        
        if assess_type:
            query += " AND s.ASSESS_TYPE = :assess_type"
            params["assess_type"] = assess_type
        
        cursor = db.execute(text(query), params)
        result = cursor.mappings().fetchall()
        
        return [
            {
                "patient_id": row["PATIENT_ID"],
                "order_num": row["ORDER_NUM"],
                "assess_type": row["ASSESS_TYPE"],
                "question_cd": row["QUESTION_CD"],
                "score": float(row["SCORE"]) if row["SCORE"] is not None else 0,
            }
            for row in result
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"점수 조회 실패: {str(e)}")
