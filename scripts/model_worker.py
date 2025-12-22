import os
import sys
import time
import logging
from pathlib import Path
import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv

# 프로젝트 루트 경로 설정
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "ui"))
sys.path.append(str(ROOT))

# 환경변수 로드
load_dotenv(dotenv_path=ROOT / ".env", override=True)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# DB 세션
from api.database import SessionLocal
from ui.services.model_service import model_process
from ui.services.db_service import save_scores_to_db


def get_pending_jobs(db):
    """점수가 없는 회차 중 파일이 존재하는 건만 조회"""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT lst.PATIENT_ID, lst.ORDER_NUM, pk.API_KEY
            FROM assess_lst lst
            JOIN assess_file_lst f
              ON f.PATIENT_ID = lst.PATIENT_ID
             AND f.ORDER_NUM = lst.ORDER_NUM
             AND f.USE_YN = 'Y'
            LEFT JOIN assess_score s
              ON s.PATIENT_ID = lst.PATIENT_ID
             AND s.ORDER_NUM = lst.ORDER_NUM
            LEFT JOIN patient_api_key pk
              ON pk.PATIENT_ID = lst.PATIENT_ID
            WHERE s.PATIENT_ID IS NULL
            """
        )
    ).fetchall()
    return rows


def fetch_path_info(db, patient_id: str, order_num: int) -> pd.DataFrame:
    """assess_file_lst 메타데이터를 DataFrame으로 구성"""
    query = text(
        """
        SELECT 
            PATIENT_ID as patient_id,
            ORDER_NUM as order_num,
            ASSESS_TYPE as assess_type,
            QUESTION_CD as question_cd,
            QUESTION_NO as question_no,
            QUESTION_MINOR_NO as question_minor_no
        FROM assess_file_lst
        WHERE PATIENT_ID = :patient_id
          AND ORDER_NUM = :order_num
          AND USE_YN = 'Y'
        ORDER BY ASSESS_TYPE, QUESTION_CD, QUESTION_NO, QUESTION_MINOR_NO
        """
    )
    df = pd.read_sql(query, db.connection(), params={"patient_id": patient_id, "order_num": order_num})
    return df


def process_pending_jobs():
    db = SessionLocal()
    try:
        pending = get_pending_jobs(db)
        if not pending:
            logger.info("대기 중인 모델링 작업이 없습니다.")
            return

        logger.info(f"{len(pending)}건 처리 시작")
        for patient_id, order_num, api_key in pending:
            try:
                # 이미 점수가 있으면 건너뜀 (이중 실행 방지)
                score_exists = db.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM assess_score
                        WHERE PATIENT_ID = :patient_id AND ORDER_NUM = :order_num
                        """
                    ),
                    {"patient_id": patient_id, "order_num": order_num}
                ).scalar()
                if score_exists:
                    logger.info(f"{patient_id}/{order_num}: 점수 이미 존재, 건너뜀")
                    continue

                path_info = fetch_path_info(db, patient_id, order_num)
                if path_info.empty:
                    logger.warning(f"{patient_id}/{order_num}: 파일 메타데이터 없음, 건너뜀")
                    continue
                scores = model_process(path_info, api_key)
                save_scores_to_db(scores, order_num, patient_id)
                logger.info(f"{patient_id}/{order_num}: 모델링 완료 및 점수 저장")
            except Exception as e:
                logger.error(f"{patient_id}/{order_num}: 처리 실패 - {e}")
    finally:
        db.close()


def main(loop: bool = True, interval: int = 300):
    if not loop:
        process_pending_jobs()
        return

    logger.info(f"모델 워커 시작 (주기: {interval}초)")
    while True:
        process_pending_jobs()
        time.sleep(interval)


if __name__ == "__main__":
    main(loop=True, interval=300)
