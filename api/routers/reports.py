from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from io import BytesIO
import tarfile
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ..database import get_db

router = APIRouter()

# 특정 환자의 모든 검사 결과(리포트) 조회
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
                sc.PATIENT_ID,
                sc.ORDER_NUM,
                sc.ASSESS_TYPE,
                sc.QUESTION_CD,
                sc.QUESTION_NO,
                sc.QUESTION_MINOR_NO,
                sc.SCORE
            FROM AUDIO_STORAGE sc
            WHERE sc.PATIENT_ID = :patient_id
              AND sc.USE_TF = 1
              AND (:assess_type IS NULL OR sc.ASSESS_TYPE = :assess_type)
        """)
        assess_cursor = db.execute(
            assess_query,
            {
                "patient_id": patient_id,
                "assess_type": assess_type
            }
        )
        rows = assess_cursor.mappings().fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="검사 기록을 찾을 수 없습니다")

        return [
            {
                "patient_id": row["PATIENT_ID"],
                "order_num": row["ORDER_NUM"],
                "assess_type": row["ASSESS_TYPE"],
                "question_cd": row["QUESTION_CD"],
                "question_no": row["QUESTION_NO"],
                "question_minor_no": row["QUESTION_MINOR_NO"],
                "score": row["SCORE"]
            }
            for row in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리포트 조회 실패: {str(e)}")

# 모델링용 메타데이터 불러오기: 이미 진행된 경우는 제외(use_tf)
@router.get("/{patient_id}/{order_num}/metadata")
def get_assessment(
    patient_id,
    order_num,
    db: Session = Depends(get_db)
):
    assess_query = text("""

        SELECT 
            sc.PATIENT_ID,
            sc.ORDER_NUM,
            sc.ASSESS_TYPE,
            sc.QUESTION_CD,
            sc.QUESTION_NO,
            sc.QUESTION_MINOR_NO,
            sc.SCORE,
            sc.DURATION,
            sc.RATE
        FROM AUDIO_STORAGE sc
        WHERE sc.PATIENT_ID = :patient_id
            AND sc.ORDER_NUM = :order_num
            AND sc.USE_TF = 0
    """)
    assess_cursor = db.execute(
        assess_query, 
        {
            "patient_id": patient_id,
            "order_num": order_num
        }
    )
    rows = assess_cursor.mappings().fetchall()
    return [
            {
                "patient_id": row["PATIENT_ID"],
                "order_num": row["ORDER_NUM"],
                "assess_type": row["ASSESS_TYPE"],
                "question_cd": row["QUESTION_CD"],
                "filename": row['QUESTION_NO']+'_'+row['QUESTION_MINOR_NO'],
                "score": row["SCORE"],
                "duration": row["DURATION"],
                "rate": row["RATE"],
            }
            for row in rows
        ]

# 모델링용 파일만 불러오기: 이미 진행된 경우는 제외(use_tf)
# @router.get("/{patient_id}/{order_num}/files")
# def get_assessment_files(
#     patient_id,
#     order_num,
#     db: Session = Depends(get_db)
# ):
    assess_query = text("""

        SELECT 
            FILE
        FROM AUDIO_STORAGE 
        WHERE PATIENT_ID = :patient_id
            AND ORDER_NUM = :order_num
            AND USE_TF = 0
    """)
    assess_cursor = db.execute(
        assess_query, 
        {
            "patient_id": patient_id,
            "order_num": order_num
        }
    )
    rows = assess_cursor.mappings().fetchall()
    return [
            {
                "file": row["FILE"]
            }
            for row in rows
        ]

@router.get("/{patient_id}/{order_num}/bundle")
def get_assessment_bundle(
    patient_id: str,
    order_num: int,
    db: Session = Depends(get_db),
):
    # 1) 메타데이터 + BLOB 조회
    query = text("""
        SELECT 
            PATIENT_ID,
            ORDER_NUM,
            ASSESS_TYPE,
            QUESTION_CD,
            QUESTION_NO,
            QUESTION_MINOR_NO,
            DURATION,
            RATE,
            FILE
        FROM AUDIO_STORAGE
        WHERE PATIENT_ID = :patient_id
          AND ORDER_NUM = :order_num
          AND USE_TF = 0
        ORDER BY ASSESS_TYPE, QUESTION_CD, QUESTION_NO, QUESTION_MINOR_NO
    """)

    rows = db.execute(query, {
        "patient_id": patient_id,
        "order_num": order_num,
    }).mappings().fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="해당 회차의 파일이 없습니다")

    # 2) tar.gz 메모리 번들 생성
    buf = BytesIO()
    with tarfile.open(mode="w:gz", fileobj=buf) as tar:
        manifest = []

        for idx, row in enumerate(rows):
            # manifest용 메타데이터
            item = {
                "patient_id": row["PATIENT_ID"],
                "order_num": row["ORDER_NUM"],
                "assess_type": row["ASSESS_TYPE"],
                "question_cd": row["QUESTION_CD"],
                "question_no": row["QUESTION_NO"],
                "question_minor_no": row["QUESTION_MINOR_NO"],
                "duration": row["DURATION"],
                "rate": row["RATE"],
                # 번들 안에서의 경로
                "relative_path": f"audio/{row['QUESTION_CD']}/{row['QUESTION_NO']}_{row['QUESTION_MINOR_NO']}.wav",
            }
            manifest.append(item)

            # 오디오 파일 추가
            audio_bytes: bytes = row["FILE"]
            file_obj = BytesIO(audio_bytes)

            info = tarfile.TarInfo(name=item["relative_path"])
            info.size = len(audio_bytes)
            tar.addfile(info, fileobj=file_obj)

        # manifest.json 추가
        manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        manifest_info = tarfile.TarInfo(name="manifest.json")
        manifest_info.size = len(manifest_bytes)
        tar.addfile(manifest_info, fileobj=BytesIO(manifest_bytes))

    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{patient_id}_{order_num}_bundle.tar.gz"'
        },
    )