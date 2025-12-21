from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..database import get_db

router = APIRouter()

@router.get("/")
def get_patients(db: Session = Depends(get_db)):
    """전체 환자 목록 조회"""
    try:
        query = text("""
            SELECT DISTINCT p.PATIENT_ID, 
                   COALESCE(pi.NAME, '정보없음') as PATIENT_NAME, 
                   p.AGE, 
                   COALESCE(pi.SEX, '0') as SEX
            FROM assess_lst p
            LEFT JOIN patient_info pi ON p.PATIENT_ID = pi.PATIENT_ID
            ORDER BY p.PATIENT_ID
        """)
        
        cursor = db.execute(query)
        result = cursor.fetchall()
        
        return [
            {
                "patient_id": row[0],
                "patient_name": row[1],
                "age": row[2],
                "sex": row[3]
            }
            for row in result
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"환자 목록 조회 실패: {str(e)}")

@router.get("/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    """특정 환자 정보 조회 (patient_info 전체 필드 반환)"""
    try:
        query = text("""
            SELECT PATIENT_ID,
                   CODE,
                   NAME,
                   AGE,
                   SEX,
                   EDU,
                   EXCLUDED,
                   POST_STROKE_DATE,
                   DIAGNOSIS,
                   STROKE_TYPE,
                   LESION_LOCATION,
                   HEMIPLEGIA,
                   HEMINEGLECT,
                   VISUAL_FIELD_DEFECT,
                   CREATE_DATE,
                   UPDATE_DATE
            FROM patient_info
            WHERE PATIENT_ID = :patient_id
        """)
        
        result = db.execute(query, {"patient_id": patient_id}).mappings().fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="환자를 찾을 수 없습니다")
        
        return {
            "patient_id": result["PATIENT_ID"],
            "code": result["CODE"],
            "name": result["NAME"],
            "patient_name": result["NAME"],  # 기존 응답과 호환용
            "age": result["AGE"],
            "sex": result["SEX"],
            "edu": result["EDU"],
            "excluded": result["EXCLUDED"],
            "post_stroke_date": str(result["POST_STROKE_DATE"]) if result["POST_STROKE_DATE"] else None,
            "diagnosis": result["DIAGNOSIS"],
            "stroke_type": result["STROKE_TYPE"],
            "lesion_location": result["LESION_LOCATION"],
            "hemiplegia": result["HEMIPLEGIA"],
            "hemineglect": result["HEMINEGLECT"],
            "visual_field_defect": result["VISUAL_FIELD_DEFECT"],
            "create_date": str(result["CREATE_DATE"]) if result["CREATE_DATE"] else None,
            "update_date": str(result["UPDATE_DATE"]) if result["UPDATE_DATE"] else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"환자 정보 조회 실패: {str(e)}")
