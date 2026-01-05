from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..database import get_db

router = APIRouter()

@router.get("/reports/{patient_id}/{api_key}")
def get_report(
    patient_id: str,
    api_key: str,
    db: Session = Depends(get_db)
):
    """검사 리포트 전체 데이터 조회"""
    try:
        api_check_query = text("""
            SELECT API_KEY
            FROM patient_api_key
            WHERE API_KEY = :api_key
        """)
        api_check_cursor = db.execute(
            api_check_query, 
            {"api_key": api_key}
        )
        api_check_info = api_check_cursor.mappings().fetchone()
        if not api_check_info:
            raise HTTPException(status_code=404, detail="API 키를 찾을 수 없습니다")

        assess_query = text("""
            SELECT distinct
                sc.PATIENT_ID, 
                sc.ASSESS_TYPE,
                sc.QUESTION_CD,
                sc.QUESTION_NO,
                sc.QUESTION_MINOR_NO,
                sc.SCORE,
                sc.NOTE,
                sc.CREATE_DATE,
                cd.SUB_CD_NM as QUESTION_NM
            FROM assess_score sc
            WHERE sc.PATIENT_ID = :patient_id AND psk.API_KEY = :api_key AND sc.USE_YN = 'Y'
            order by sc.create_date desc
        """)
        assess_cursor = db.execute(
            assess_query, 
            {"patient_id": patient_id, "api_key": api_key}
        )
        assess_info = assess_cursor.mappings().fetchone()
        
        if not assess_info:
            raise HTTPException(status_code=404, detail="검사 기록을 찾을 수 없습니다")
        
        return {
            "assess_info": [
                {
                    "patient_id": row["PATIENT_ID"],
                    "assess_type": row["ASSESS_TYPE"],
                    "question_cd": row["QUESTION_CD"],
                    "question_no": row["QUESTION_NO"],
                    "question_minor_no": row["QUESTION_MINOR_NO"],
                    "score": row["SCORE"],
                    "note": row["NOTE"],
                    "create_date": row["CREATE_DATE"],
                    "question_nm": row["QUESTION_NM"]
                }
                for row in assess_info
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리포트 조회 실패: {str(e)}")
