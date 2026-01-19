from fastapi import APIRouter, Depends, HTTPException
from ..models import PatientCreate, PatientInfo
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..database import get_db

router = APIRouter()

@router.get("/", response_model=List[PatientInfo])
def get_patients(db: Session = Depends(get_db)):
    """전체 환자 목록 조회"""
    try:
        query = text("""
            SELECT DISTINCT p.PN, p.NAME
            FROM user p
            ORDER BY p.PN
        """)
        
        cursor = db.execute(query)
        result = cursor.fetchall()
        
        return [
            {
                "patient_id": row[0],
                "patient_name": row[1]
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
            SELECT ID,
                NAME,
                PN,
                AGE,
                GENDER,
                YEAR,
                MONTH,
                DAY,
                HIGHEST_EDUCATION,
                GRADE,
                YEAR1,
                grammar,
                CATEGORY,
                AGENCY,
                ETC,
                DIALECT,
                YEAR_OF_DISEASE,
                DAY_OF_DISEASE,
                AGE_OF_DISEASE
            FROM user
            WHERE PN = :patient_id
        """)
        
        result = db.execute(query, {"patient_id": patient_id}).mappings().fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="환자를 찾을 수 없습니다")
        
        return {
            "id": result["id"],
            "name": result["NAME"],
            "age": result["AGE"],
            "gender": result["GENDER"],
            "year":result['YEAR'],
            "month":result['MONTH'],
            "day":result['DAY'],
            "highest_education":result['HIGHEST_EDUCATION'],
            "grade":result['GRADE'],
            "year1":result['YEAR1'],
            "grammar":result['GRAMMAR'],
            "category":result['CATEGORY'],
            "agency":result['AGENCY'],
            "etc":result['ETC'],
            "dialect":result['DIALECT'],
            "year_of_disease":result['YEAR_OF_DISEASE'],
            "day_of_disease":result['DAY_OF_DISEASE'],
            "age_of_disease":result['AGE_OF_DISEASE'],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"환자 정보 조회 실패: {str(e)}")

# 환자 정보 등록
@router.post("/") 
def register_patient(patient: PatientCreate, db: Session = Depends(get_db)):
    try:
        # 1. SQL INSERT 쿼리 작성
        query = text("""
            INSERT INTO user (
                ID, NAME, PN, AGE, GENDER, YEAR, MONTH, DAY, 
                HIGHEST_EDUCATION, GRADE, YEAR1, GRAMMER, 
                CATEGORY, AGENCY, ETC, DIALECT, 
                YEAR_OF_DISEASE, DAY_OF_DISEASE, AGE_OF_DISEASE
            ) VALUES (
                :ID, :NAME, :PN, :AGE, :GENDER, :YEAR, :MONTH, :DAY, 
                :HIGHEST_EDUCATION, :GRADE, :YEAR1, :GRAMMER, 
                :CATEGORY, :AGENCY, :ETC, :DIALECT, 
                :YEAR_OF_DISEASE, :DAY_OF_DISEASE, :AGE_OF_DISEASE
            )
        """)

        # 2. 쿼리 실행
        result = db.execute(query, patient.dict())
        db.commit() # 중요: 데이터 저장 확정

        # # 3. 새로 생성된 ID 가져오기 (필요한 경우)
        # new_id = result.lastrowid

        # 4. 안드로이드 PatientInfoResponse 형식에 맞춰 반환
        return {
            "id": patient.ID,
            "name": patient.NAME,
            "pn": patient.PN,
            "message": "환자 등록 성공"
        }

    except Exception as e:
        db.rollback() # 에러 발생 시 롤백
        raise HTTPException(status_code=500, detail=f"환자 등록 실패: {str(e)}")        
