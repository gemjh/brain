from dotenv import load_dotenv
from pathlib import Path
import os
import logging
import streamlit as st
from datetime import datetime
import zipfile
import wave
import pandas as pd
import re
import requests
from typing import Tuple, Optional
import tempfile
import shutil
from pydub import AudioSegment
from pydub.utils import mediainfo
import json

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 환경변수 로드
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "api_base.json"


def _get_api_base_url() -> str:
    """환경변수(.env) 우선, 없으면 config/api_base.json"""
    # 1순위: .env / 환경 변수
    env_url = os.getenv("API_BASE_URL", "").strip()
    if env_url:
        return env_url

    # 2순위: config/api_base.json
    try:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
                url = str(data.get("api_base_url", "")).strip()
                if url:
                    return url
    except Exception as e:
        logger.warning(f"api_base.json 로드 실패, 기본값 사용: {e}")

    # 3순위: 기본값
    return "http://localhost:8000/api/v1"

def _normalize_url(url: str) -> str:
    """스킴이 없으면 http:// 를 붙여 requests 에러(No connection adapters) 방지"""
    url = url.strip()
    if not url:
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"http://{url}"

API_BASE_URL = _normalize_url(_get_api_base_url())

# 검사 타입 코드 매핑
clap_A_cd = {'3':'LTN_RPT', '4':'GUESS_END', '5':'SAY_OBJ', '6':'SAY_ANI', '7':'TALK_PIC'}
clap_D_cd = {'0':'AH_SOUND', '1':'PTK_SOUND', '2':'TALK_CLEAN', '3':'READ_CLEAN'}
clap_D_pkt_cd = {1:'P_SOUND', 2:'T_SOUND', 3:'K_SOUND', 4:'PTK_SOUND'}

class APIClient:
    """API 통신 클라이언트"""

    @staticmethod
    def upload_file_with_metadata(
        patient_id: str,
        assess_type: str,
        question_cd: str,
        question_no: int,
        question_minor_no: int,
        duration: float,
        rate: int,
        file_path: str
    ) -> bool:
        """
        단일 파일을 blob으로 업로드
        """
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (os.path.basename(file_path), f, 'audio/wav')}
                data = {
                    'patient_id': patient_id,
                    'order_num': order_num,
                    'assess_type': assess_type,
                    'question_cd': question_cd,
                    'question_no': question_no,
                    'question_minor_no': question_minor_no,
                    'duration': duration,
                    'rate': rate
                }
                
            response = requests.post(
                f"{API_BASE_URL}/assessments/files/upload",
                files=files,
                data=data,
                timeout=120
            )
            response.raise_for_status()
            logger.info(f"파일 업로드 완료: {os.path.basename(file_path)}")
            return True
        except Exception as e:
            logger.error(f"파일 업로드 실패: {e}")
            return False
    
    @staticmethod
    def upload_files_bulk(files_data: list) -> Tuple[bool, Optional[str]]:
        """
        여러 파일을 한번에 blob으로 업로드
        각 파일을 개별적으로 업로드하는 방식으로 변경
        
        Args:
            files_data: [{'file_path': str, 'metadata': dict}, ...]
        """
        try:
            success_count = 0
            api_key = None
            first_patient_id = files_data[0]['metadata']['patient_id'] if files_data else None
            
            for item in files_data:
                file_path = item['file_path']
                metadata = item['metadata']
                
                # 개별 파일 업로드
                try:
                    with open(file_path, 'rb') as f:
                        files = {'file': (os.path.basename(file_path), f, 'audio/wav')}
                        params = {
                            'patient_id': metadata['patient_id'],
                            'order_num': metadata['order_num'],
                            'assess_type': metadata['assess_type'],
                            'question_cd': metadata['question_cd'],
                            'question_no': metadata['question_no'],
                            'question_minor_no': metadata['question_minor_no'],
                            'duration': metadata['duration'],
                            'rate': metadata['rate']
                        }
                        
                        response = requests.post(
                            f"{API_BASE_URL}/assessments/files/upload",
                            files=files,
                            params=params,
                            timeout=120
                        )
                        if response.status_code >= 400:
                            try:
                                err_detail = response.json()
                            except Exception:
                                err_detail = response.text
                            raise requests.HTTPError(f"{response.status_code} {response.reason}: {err_detail}")
                        if api_key is None:
                            try:
                                api_key = response.json().get("api_key")
                            except Exception:
                                api_key = None
                        success_count += 1
                        
                except Exception as e:
                    logger.error(f"파일 업로드 실패: {os.path.basename(file_path)}, {e}")
                    # 개별 파일 실패는 계속 진행
                    continue
            
            logger.info(f"파일 일괄 업로드 완료: {success_count}/{len(files_data)}건")

            # 업로드 응답에 키가 없으면 DB에서 조회해서 보정
            if api_key is None and first_patient_id:
                api_key = APIClient.get_api_key_by_patient(first_patient_id)
                if api_key:
                    logger.info(f"DB에서 API Key 보정: {api_key}")
                else:
                    logger.warning("API Key를 발급/조회하지 못했습니다. 업로드는 진행되었을 수 있습니다.")
            
            # 최소 1개 이상 성공하면 True
            return success_count > 0, api_key
            
        except Exception as e:
            logger.error(f"파일 일괄 업로드 실패: {e}")
            return False, None

    @staticmethod
    def cleanup_assessment(patient_id: str, order_num: int, api_key: Optional[str] = None) -> None:
        """업로드 실패 시 생성된 DB 데이터 롤백"""
        try:
            headers = {"X-API-KEY": api_key} if api_key else None
            response = requests.delete(
                f"{API_BASE_URL}/assessments/{patient_id}/{order_num}",
                headers=headers,
                timeout=120
            )
            response.raise_for_status()
            logger.info(f"롤백 완료: {patient_id}, 회차 {order_num}")
        except requests.exceptions.RequestException as e:
            logger.error(f"롤백 실패 (무시하고 진행): {e}")
    
    @staticmethod
    def handle_duplicate_files(patient_id: str, order_num: int, api_key: Optional[str]) -> bool:
        """중복 처리 단계는 비활성화 (항상 성공으로 간주)"""
        logger.info("중복 파일 처리 스킵")
        return True
    
    @staticmethod
    def initialize_scores(patient_id: str, order_num: int, api_key: Optional[str]) -> bool:
        """점수 테이블 초기화"""
        try:
            if api_key is None:
                api_key = APIClient.get_api_key_by_patient(patient_id)
            headers = {"X-API-KEY": api_key} if api_key else None
            response = requests.post(
                f"{API_BASE_URL}/assessments/{patient_id}/{order_num}/init-scores",
                headers=headers,
                timeout=120
            )
            response.raise_for_status()
            logger.info(f"점수 테이블 초기화 완료: {patient_id}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"점수 테이블 초기화 실패: {e}")
            return False


def parse_csv_file(csv_path: str) -> dict:
    """CSV 파일 파싱"""
    df = pd.read_csv(csv_path)
    pattern = r'^-?\d+(\.\d+)?'
    """CSV 파일 파싱"""
    df = pd.read_csv(csv_path)
    pattern = r'^-?\d+(\.\d+)?$'
    
    csv_data = {}
    for idx in range(len(df)):
        csv_data['request_org'] = str(df.loc[idx, '대상기관'])[:10] if not pd.isna(df.loc[idx, '대상기관']) else None
        csv_data['assess_date'] = str(df.loc[idx, '검사일자'])[:10] if not pd.isna(df.loc[idx, '검사일자']) else None
        csv_data['assess_person'] = df.loc[idx, '검사자'] if not pd.isna(df.loc[idx, '검사자']) else None
        csv_data['edu'] = int(df.loc[idx, 'edu']) if not pd.isna(df.loc[idx, 'edu']) else None
        csv_data['excluded'] = str(int(df.loc[idx, 'excluded'])) if not pd.isna(df.loc[idx, 'excluded']) else '0'
        csv_data['post_stroke_date'] = str(df.loc[idx, 'post_stroke_date'])[:10] if not pd.isna(df.loc[idx, 'post_stroke_date']) else None
        
        diagnosis = df.loc[idx, 'diagnosis'] if not pd.isna(df.loc[idx, 'diagnosis']) else None
        if diagnosis and not bool(re.match(pattern, str(diagnosis))):
            csv_data['diagnosis_etc'] = str(diagnosis)
            csv_data['diagnosis'] = '4'
        elif diagnosis:
            csv_data['diagnosis'] = str(int(diagnosis))
            csv_data['diagnosis_etc'] = None
        else:
            csv_data['diagnosis'] = None
            csv_data['diagnosis_etc'] = None
        
        csv_data['stroke_type'] = str(int(df.loc[idx, 'stroke_type'])) if not pd.isna(df.loc[idx, 'stroke_type']) else None
        
        lesion_location = df.loc[idx, 'lesion_location'] if not pd.isna(df.loc[idx, 'lesion_location']) else None
        if lesion_location and bool(re.match(pattern, str(lesion_location))):
            csv_data['lesion_location'] = str(int(float(lesion_location)))
        elif lesion_location:
            csv_data['lesion_location'] = str(lesion_location)
        else:
            csv_data['lesion_location'] = None
        
        hemiplegia = df.loc[idx, 'hemiplegia'] if not pd.isna(df.loc[idx, 'hemiplegia']) else None
        if hemiplegia and bool(re.match(pattern, str(hemiplegia))):
            csv_data['hemiplegia'] = str(int(hemiplegia))
        elif hemiplegia:
            csv_data['hemiplegia'] = str(hemiplegia)
        else:
            csv_data['hemiplegia'] = None
        
        csv_data['hemineglect'] = str(int(df.loc[idx, 'hemineglect'])) if not pd.isna(df.loc[idx, 'hemineglect']) else None
        csv_data['visual_field_defect'] = str(int(df.loc[idx, 'visual field defect'])) if not pd.isna(df.loc[idx, 'visual field defect']) else None
        
        break
    
    return csv_data

def convert_to_wav(file_path: str) -> str:
    """
    m4a 파일을 wav로 변환
    
    Args:
        file_path: 원본 파일 경로
    
    Returns:
        str: 변환된 wav 파일 경로 (임시 파일)
    """
    file_ext = os.path.splitext(file_path)[1].lower()
    
    # 이미 wav면 그대로 반환
    if file_ext == '.wav':
        return file_path
    
    try:
        # m4a를 wav로 변환
        audio = AudioSegment.from_file(file_path, format='m4a')
        
        # 임시 wav 파일 생성
        temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        temp_wav.close()
        
        # wav로 내보내기 (16kHz, mono, 16bit)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        audio.export(temp_wav.name, format='wav')
        
        logger.info(f"파일 변환 완료: {os.path.basename(file_path)} -> {os.path.basename(temp_wav.name)}")
        return temp_wav.name
    
    except Exception as e:
        logger.error(f"파일 변환 실패 ({file_path}): {e}")
        raise

def get_audio_info(file_path: str) -> Tuple[float, int]:
    """
    오디오 파일 정보 추출 (wav, m4a 모두 지원)
    
    Args:
        file_path: 오디오 파일 경로
    
    Returns:
        Tuple[duration, sample_rate]: 길이(초), 샘플링 레이트
    """
    file_ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if file_ext == '.wav':
            # WAV 파일 처리
            with wave.open(file_path, 'rb') as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
                return duration, rate
        
        elif file_ext in ['.m4a', '.mp4', '.aac']:
            # M4A/AAC 파일 처리
            audio = AudioSegment.from_file(file_path, format='m4a')
            duration = len(audio) / 1000.0  # milliseconds to seconds
            rate = audio.frame_rate
            return duration, rate
        
        else:
            raise ValueError(f"지원하지 않는 오디오 포맷: {file_ext}")
    
    except Exception as e:
        logger.error(f"오디오 정보 추출 실패 ({file_path}): {e}")
        raise

def process_wav_files(target_path: str, patient_id: str, order_num: int) -> list:
    """
    오디오 파일 수집 및 메타데이터 준비 (wav, m4a 모두 지원)
    
    Returns:
        [{'file_path': str, 'metadata': dict, 'needs_conversion': bool}, ...]
    """
    files_data = []

    # 폴더명이 숫자만 있을 경우 두 폴더 중 작은 값을 CLAP_A, 큰 값을 CLAP_D로 매핑
    all_folders = [
        f for f in os.listdir(target_path)
        if os.path.isdir(os.path.join(target_path, f)) and not f.startswith("__MAC")
    ]
    # 유효 폴더 수가 2개가 아니면 오류
    if len(all_folders) != 2:
        raise ValueError(f"압축 내부 최상위 폴더는 2개(CLAP_A/CLAP_D)여야 합니다. 현재 {len(all_folders)}개 발견됨: {all_folders}")

    numeric_folders = sorted([f for f in all_folders if f.isdigit()], key=lambda x: int(x))
    numeric_mapping = {}
    if len(numeric_folders) >= 2:
        numeric_mapping[numeric_folders[0]] = 'CLAP_A'
        numeric_mapping[numeric_folders[-1]] = 'CLAP_D'

    # 명시적 폴더명 매핑과 숫자 매핑을 합침
    folder_mapping = {
        'CLAP_A': 'CLAP_A',
        'CLAP_D': 'CLAP_D',
        **numeric_mapping
    }

    for folder_name in all_folders:
        clap_type = folder_mapping.get(folder_name)
        if not clap_type:
            continue

        clap_path = os.path.join(target_path, folder_name)
        if not os.path.isdir(clap_path):
            continue

        clap_list = os.listdir(clap_path)
        code_dict = clap_A_cd if clap_type == 'CLAP_A' else clap_D_cd
        
        for clap_item in clap_list:
            # question별 하위 폴더만 처리 (p_로 시작하는 파일이 직접 들어있는 구조)
            if clap_item not in code_dict:
                continue
            
            item_path = os.path.join(clap_path,clap_item)
            if not os.path.isdir(item_path):
                logger.debug(f"폴더가 아닌 항목 건너뜀: {item_path}")
                continue
            sub_list = os.listdir(item_path)
            for filename in sub_list:
                # p_로 시작하고 wav 또는 m4a 파일만 처리
                if not filename.startswith('p_'):
                    continue
                
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext not in ['.wav', '.m4a', '.mp4', '.aac']:
                    continue
                
                file_path = os.path.join(item_path, filename)
                
                try:
                    # 오디오 정보 추출
                    duration, rate = get_audio_info(file_path)
                    
                    # 파일명 파싱
                    base_name = os.path.splitext(filename)[0]
                    spl_item = base_name.split('_')
                    question_no = int(spl_item[1])
                    question_minor_no = int(spl_item[2][0]) if len(spl_item) > 2 else 0
                    
                    # QUESTION_CD 결정
                    if clap_type == 'CLAP_D' and clap_item == '1':
                        pkt_idx = int((question_no + 2) / 3)
                        question_cd = clap_D_pkt_cd.get(pkt_idx)
                    else:
                        question_cd = code_dict.get(clap_item)

                    if not question_cd:
                        raise ValueError(f"질문 코드 매핑 실패: folder={clap_item}, file={filename}")
                    
                    files_data.append({
                        'file_path': file_path,
                        'original_filename': filename,
                        'needs_conversion': file_ext != '.wav',
                        'metadata': {
                            'patient_id': patient_id,
                            'order_num': order_num,
                            'assess_type': clap_type,
                            'question_cd': question_cd,
                            'question_no': question_no,
                            'question_minor_no': question_minor_no,
                            'duration': round(duration, 2),
                            'rate': rate
                        }
                    })
                    
                except Exception as e:
                    logger.warning(f"파일 처리 실패 (건너뜀): {filename}, {e}")
                    continue
    
    return files_data


def zip_upload(btn_apply: bool, patient_id: str, uploaded_file) -> Tuple[Optional[str], Optional[pd.DataFrame], Optional[str]]:
    """
    파일 정보를 DB에서 조회하여 모델링/업로드 처리를 수행
    
    Returns:
        Tuple[order_num, DataFrame]: 성공 시 회차 번호와 파일 정보 DataFrame
    """
    if not (btn_apply and patient_id and uploaded_file):
        return None, None
    
    logger.info("[START] 업로드 프로세스 시작 (압축 해제 없음, DB 메타데이터 사용)")
    api_key = None
    try:
        # DB에 이미 저장된 파일 메타데이터를 사용 (create_date 내림차순)
        files = APIClient.get_assessment_files(patient_id, order_num=0)
        if not files:
            raise Exception("DB에 파일 메타데이터가 없습니다")
        df = pd.DataFrame(files).sort_values(by="CREATE_DATE", ascending=False)

        # 중복 파일 처리
        api_key = APIClient.get_api_key_by_patient(patient_id)
        if not APIClient.handle_duplicate_files(patient_id, order_num=0, api_key=api_key):
            raise Exception("중복 파일 처리 실패")

        # 점수 테이블 초기화
        if not APIClient.initialize_scores(patient_id, order_num=0, api_key=api_key):
            raise Exception("점수 테이블 초기화 실패")

        logger.info(f"[COMPLETE] 업로드 완료: {patient_id}")
        return "0", df, api_key

    except Exception as e:
        logger.error(f"[ERROR] 업로드 실패: {str(e)}")
        st.error(f"업로드 중 오류 발생: {str(e)}")
        return None, None, None

    
