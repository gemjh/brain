import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# .env를 명시적으로 프로젝트 루트에서 로드 (override=True로 기존 값 덮어쓰기)
_ROOT_DIR = Path(__file__).resolve().parents[2]
_ENV_PATH = _ROOT_DIR / ".env"
_CONFIG_PATH = _ROOT_DIR / "config" / "api_base.json"
load_dotenv(dotenv_path=_ENV_PATH, override=True)

# 기본값 (환경 변수)
_DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1").strip()
logger = logging.getLogger(__name__)


class APIClient:    
    @staticmethod
    def _get_api_base_url() -> str:
        """
        API_BASE_URL을 우선 환경 변수(.env)에서 읽고,
        없으면 config/api_base.json을 사용한다.
        """
        # 1순위: .env / 환경 변수
        env_url = os.getenv("API_BASE_URL", "").strip()
        if env_url:
            return env_url

        # 2순위: config/api_base.json
        try:
            if _CONFIG_PATH.exists():
                with _CONFIG_PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    url = str(data.get("api_base_url", "")).strip()
                    if url:
                        return url
        except Exception as e:
            logger.warning(f"api_base.json 로드 실패, 기본값 사용: {e}")

        # 3순위: 기본값
        return _DEFAULT_API_BASE_URL

    @staticmethod
    def _normalize_url(url: str) -> str:
        """스킴이 없으면 http:// 를 붙여 requests 에러(No connection adapters) 방지"""
        url = url.strip()
        if not url:
            return url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"http://{url}"

    # ============================================
    # 공통 메서드
    # ============================================
    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout))
    )
    def _make_request(method: str, endpoint: str, **kwargs):
        """
        공통 요청 메서드 (retry 로직 포함)
        
        Args:
            method: HTTP 메서드 (GET, POST, PUT, DELETE)
            endpoint: API 엔드포인트 경로
            **kwargs: requests 라이브러리 파라미터
        
        Returns:
            dict: JSON 응답
        """
        raw_base_url = APIClient._get_api_base_url()
        base_url = APIClient._normalize_url(raw_base_url)
        url = f"{base_url}{endpoint}"
        logger.debug(f"API 요청: {method} {url}")
        timeout = kwargs.pop('timeout', 120)
        
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"API 요청 타임아웃: {url}")
            raise Exception(f"서버 응답 시간 초과: {endpoint}")
        except requests.exceptions.ConnectionError:
            logger.error(f"API 연결 실패: {url}")
            raise Exception(f"서버에 연결할 수 없습니다: {endpoint}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"API 요청 실패: {url}, 상태코드: {e.response.status_code}")
            raise Exception(f"API 오류 ({e.response.status_code}): {endpoint}")
        except requests.exceptions.RequestException as e:
            logger.error(f"API 요청 실패: {url}, 오류: {e}")
            raise Exception(f"API 요청 실패: {str(e)}")
    
    # ============================================
    # 환자 관련
    # ============================================
    @staticmethod
    def get_patients() -> List[Dict]:
        """환자 목록 조회"""
        return APIClient._make_request("GET", "/patients")
    
    @staticmethod
    def get_patient(patient_id: str) -> Dict:
        """특정 환자 조회"""
        return APIClient._make_request("GET", f"/patients/{patient_id}")
    
    @staticmethod
    def get_assessment_scores(
        patient_id: str, 
        assess_type: Optional[str] = None
    ) -> List[Dict]:
        """검사 점수 조회"""
        params = {"assess_type": assess_type} if assess_type else {}
        return APIClient._make_request(
            "GET",
            f"/reports/{patient_id}",
            params=params
        )
    
    @staticmethod
    def get_assessment_files(patient_id: str, order_num: int):
        """검사 파일 조회"""
        return APIClient._make_request(
            "GET",
            f"/reports/{patient_id}/{order_num}/files"
        )

    
    # ============================================
    # 점수 저장 (신규 추가)
    # ============================================
    @staticmethod
    def save_scores_bulk(score_list: List[Dict]) -> bool:
        """
        점수 일괄 저장

        Returns:
            bool: 저장 성공 여부
        """
        try:
            # file 키 제거 + numpy float32 → Python float 변환 (None은 유지)
            score_list = [
                {k: (float(v) if k == 'score' and v is not None else v) for k, v in item.items() if k != 'file'}
                for item in score_list
            ]
            result = APIClient._make_request(
                "POST",
                "/assessments/score",
                json={"scores": score_list}
            )
            return result.get('success', False)
        except Exception as e:
            logger.error(f"점수 저장 실패: {e}")
            return False
    
    # ============================================
    # 리포트 관련
    # ============================================
    @staticmethod
    def get_report(
        patient_id: str,
        api_key: str,
        assess_type: Optional[str] = None
    ) -> List[Dict]:
        """리포트 조회"""
        headers = {"X-API-KEY": api_key}
        params = {"assess_type": assess_type} if assess_type else None
        return APIClient._make_request(
            "GET",
            f"/reports/{patient_id}",
            headers=headers,
            params=params

        # """검사 목록 조회"""
        # params = {"assess_type": assess_type} if assess_type else {}
        # headers = {"X-API-KEY": api_key} if api_key else None
        # return APIClient._make_request(
        #     "GET", 
        #     f"/assessments/{patient_id}",
        #     params=params,
        #     headers=headers
        )
    
    # ============================================
    # 파일 업로드 관련 (신규 추가)
    # ============================================
    @staticmethod
    def upload_assessment(patient_id: str, file) -> Dict:
        """
        검사 파일 업로드
        
        Args:
            patient_id: 환자 ID
            file: 업로드할 파일 객체
        
        Returns:
            dict: 업로드 결과
        """
        try:
            files = {"file": file}
            result = APIClient._make_request(
                "POST",
                f"/assessments/{patient_id}/upload",
                files=files,
                timeout=120  # 파일 업로드는 타임아웃 길게
            )
            return result
        except Exception as e:
            logger.error(f"파일 업로드 실패: {e}")
            raise

    # ============================================
    # API Key 관련
    # ============================================
    @staticmethod
    def resolve_api_key(api_key: str) -> Dict:
        """API Key로 환자 ID 조회"""
        return APIClient._make_request("GET", f"/keys/{api_key}/patient")

    @staticmethod
    def get_api_key_by_patient(patient_id: str) -> Optional[str]:
        """환자 ID로 API Key 조회"""
        try:
            res = APIClient._make_request("GET", f"/keys/patient/{patient_id}")
            return res.get("api_key")
        except Exception as e:
            logger.error(f"API Key 조회 실패: {e}")
            return None
    
