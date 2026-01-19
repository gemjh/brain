from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import sys
import os
from fastapi import Header


sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..database import get_db

router = APIRouter()

@router.get("/{patient_id}")
def get_report(
    patient_id: str,
    api_key: str = Header(..., alias="X-API-KEY"),
    assess_type: str = None,
    db: Session = Depends(get_db)
):
    """검사 리포트 전체 데이터 조회: 등록된 api키 없으면 종료 """
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
            # 최신 1개만 조회하려면:
            # WITH latest_ord AS (
            #     SELECT MAX(ORDER_NUM) AS max_ord
            #     FROM assess_score
            #     WHERE PATIENT_ID = :patient_id
            # )
        assess_query = text("""

            SELECT DISTINCT
                sc.ID, 
                sc.PN,
                sc.ORDER_NUM,
                sc.ASSESS_TYPE,
                sc.EPISODE_CODE,
                sc.QUESTION_NO,
                sc.FILENAME,
                sc.SCORE,
                sc.CREATED_AT
            FROM score sc
            WHERE sc.PN = :patient_id
              AND (:assess_type IS NULL OR sc.ASSESS_TYPE = :assess_type)
        """)
        assess_cursor = db.execute(
            assess_query, 
            {
                "patient_id": patient_id,
                "api_key": api_key,
                "assess_type": assess_type
            }
        )
        rows = assess_cursor.mappings().fetchall()
        
        if not rows:
            raise HTTPException(status_code=404, detail="검사 기록을 찾을 수 없습니다")
        
        return [
            {
                "id": row["ID"],
                "patient_number": row["PN"],
                "order_num": row["ORDER_NUM"],
                "assess_type": row["ASSESS_TYPE"],
                "question_cd": row["EPISODE_CODE"],
                "question_no": row["QUESTION_NO"],
                "filename": row["FILENAME"],
                "score": row["SCORE"],
                "create_date": row["CREATED_AT"]
            }
            for row in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리포트 조회 실패: {str(e)}")
