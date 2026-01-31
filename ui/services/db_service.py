from services.api_client import APIClient
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)


def save_scores_to_db(fin_scores: List[Dict], order_num: int, patient_id: str, question_meta: dict) -> bool:
    """
    모델링 결과를 API를 통해 DB에 저장하는 함수

    Args:
        fin_scores: 모델링 결과 딕셔너리 {'LTN_RPT': 10, 'GUESS_END': 5, ...}
        order_num: 검사 회차 번호

    Returns:
        bool: 저장 성공 여부
    """
    try:
        if not patient_id:
            raise ValueError("patient_id가 필요합니다.")

        # 폴더 구조대로 순서 배열
        a_list = ['LTN_RPT', 'GUESS_END', 'SAY_OBJ', 'SAY_ANI', 'TALK_PIC']
        d_list = ['AH_SOUND', 'P_SOUND', 'T_SOUND', 'K_SOUND', 'PTK_SOUND', 'TALK_CLEAN']

        # 빠른 조회용 매핑
        assess_lookup = {**{k: 'CLAP-A' for k in a_list},
                        **{k: 'CLAP-D' for k in d_list}}

        # ============================================
        # 핵심 변경: DB 직접 접근 → API 호출
        # ============================================
        score_list = [{k: v for k, v in item.items() if k != 'file'} for item in fin_scores]

        result = APIClient.save_scores_bulk(score_list)

        if result:
            logger.info(f"점수 저장 완료: {patient_id} - 회차 {order_num} ({len(fin_scores)}건)")
            return True
        else:
            logger.error(f"점수 저장 실패: {patient_id}")
            return False

    except Exception as e:
        logger.error(f"점수 저장 중 오류 발생: {e}, {fin_scores}")
        return False
