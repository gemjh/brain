from pydantic import BaseModel
from typing import Optional

# 환자 정보 모델
class PatientInfo(BaseModel):
    patient_id: str
    patient_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class PatientCreate(BaseModel):
    ID: str
    NAME: str
    PN: str
    AGE: str
    GENDER: str
    YEAR: str
    MONTH: str
    DAY: str
    HIGHEST_EDUCATION: str
    GRADE: str
    YEAR1: str
    GRAMMER: str
    CATEGORY: str
    AGENCY: str
    ETC: str
    DIALECT: str
    YEAR_OF_DISEASE: str
    DAY_OF_DISEASE: str
    AGE_OF_DISEASE: str


# 검사 결과 모델
class AssessmentResult(BaseModel):
    patient_id: str
    order_num: int
    assess_type: str
    question_cd: str
    score: float
    
    class Config:
        from_attributes = True

# 검사 목록 응답 모델
class AssessmentListResponse(BaseModel):
    patient_id: str
    order_num: int
    assess_type: str
    question_cd: str
    question_no: int
    question_minor_no: int
    file_name: str
    create_date: Optional[str]
    file_content: Optional[bytes]
