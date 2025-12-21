from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..database import get_db

router = APIRouter()

@router.get("/{patient_id}")
def get_assessments(
    patient_id: str, 
    assess_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """환자의 검사 목록 조회"""
    try:
        base_query = """
            SELECT DISTINCT 
                lst.ORDER_NUM, lst.PATIENT_ID, 
                COALESCE(p.name, '정보없음') as PATIENT_NAME,
                lst.AGE, COALESCE(p.SEX, '0') as SEX, 
                flst.ASSESS_TYPE, flst.MAIN_PATH, lst.ASSESS_DATE, 
                lst.REQUEST_ORG, lst.ASSESS_PERSON
            FROM assess_lst lst
            LEFT JOIN patient_info p ON lst.PATIENT_ID = p.PATIENT_ID
            INNER JOIN assess_file_lst flst 
                ON lst.PATIENT_ID = flst.PATIENT_ID 
                AND lst.ORDER_NUM = flst.ORDER_NUM
            WHERE flst.USE_YN = 'Y'
                AND lst.PATIENT_ID = :patient_id
        """
        
        params = {"patient_id": patient_id}
        
        if assess_type:
            base_query += " AND flst.ASSESS_TYPE = :assess_type"
            params["assess_type"] = assess_type
        
        cursor = db.execute(text(base_query), params)
        result = cursor.mappings().fetchall()
        
        return [
            {
                "order_num": row["ORDER_NUM"],
                "patient_id": row["PATIENT_ID"],
                "patient_name": row["PATIENT_NAME"],
                "age": row["AGE"],
                "sex": row["SEX"],
                "assess_type": row["ASSESS_TYPE"],
                "main_path": row["MAIN_PATH"],
                "assess_date": str(row["ASSESS_DATE"]) if row["ASSESS_DATE"] else None,
                "request_org": row["REQUEST_ORG"],
                "assess_person": row["ASSESS_PERSON"]
            }
            for row in result
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검사 목록 조회 실패: {str(e)}")

@router.get("/{patient_id}/{order_num}/scores")
def get_assessment_scores(
    patient_id: str,
    order_num: int,
    assess_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """특정 검사의 점수 조회"""
    try:
        query = """
            SELECT 
                s.PATIENT_ID, s.ORDER_NUM, s.ASSESS_TYPE, 
                s.QUESTION_CD, s.SCORE
            FROM assess_score s
            WHERE s.PATIENT_ID = :patient_id 
            AND s.ORDER_NUM = :order_num
        """
        
        params = {"patient_id": patient_id, "order_num": order_num}
        
        if assess_type:
            query += " AND s.ASSESS_TYPE = :assess_type"
            params["assess_type"] = assess_type
        
        cursor = db.execute(text(query), params)
        result = cursor.fetchall()
        
        return [
            {
                "patient_id": row[0],
                "order_num": row[1],
                "assess_type": row[2],
                "question_cd": row[3],
                "score": float(row[4]) if row[4] else 0
            }
            for row in result
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"점수 조회 실패: {str(e)}")
