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
    def fetch_order_num(patient_id: str) -> int:
        """환자의 수행회차 조회 (API 호출)"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/patients/{patient_id}/order",
                timeout=150
            )
            response.raise_for_status()
            order_num = response.json().get('order_num')
            if order_num is None:
                logger.warning(f"order_num이 null로 반환됨, 기본값 1 사용: {patient_id}")
                return 1
            return int(order_num)
        except requests.exceptions.RequestException as e:
            logger.error(f"수행회차 조회 실패: {e}")
            raise Exception(f"API 호출 실패: {str(e)}")
    
    @staticmethod
    def save_patient_assessment(patient_id: str, order_num: int, csv_data: dict) -> bool:
        """환자 검사 정보 저장"""
        try:
            payload = {
                "patient_id": patient_id,
                "order_num": order_num,
                **csv_data
            }
            response = requests.post(
                f"{API_BASE_URL}/assessments/patient-info",
                json=payload,
                timeout=120
            )
            response.raise_for_status()
            logger.info(f"환자 검사 정보 저장 완료: {patient_id}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"환자 검사 정보 저장 실패: {e}")
            return False

    @staticmethod
    def get_patient_info(patient_id: str) -> Optional[dict]:
        """patient_info에서 환자 기본 정보를 가져온다."""
        try:
            response = requests.get(
                f"{API_BASE_URL}/patients/{patient_id}",
                timeout=150
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"환자 기본 정보 조회 실패: {e}")
            return None
    
    @staticmethod
    def upload_file_with_metadata(
        patient_id: str,
        order_num: int,
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
        csv_data['age'] = int(df.loc[idx, 'age']) if not pd.isna(df.loc[idx, 'age']) else None
        csv_data['sex'] = str(int(df.loc[idx, 'sex'])) if not pd.isna(df.loc[idx, 'sex']) else None
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
    ZIP 파일 업로드 및 blob으로 DB 저장
    
    Returns:
        Tuple[order_num, DataFrame]: 성공 시 회차 번호와 파일 정보 DataFrame
    """
    if not (btn_apply and patient_id and uploaded_file):
        return None, None
    
    logger.info("[START] ZIP 업로드 프로세스 시작")
    order_num = None
    # 임시 디렉토리 생성
    temp_dir = tempfile.mkdtemp()
    
    api_key = None
    try:
        # 1. 압축 해제
        zip_path = os.path.join(temp_dir, uploaded_file.name)
        with open(zip_path, 'wb') as f:
            f.write(uploaded_file.getbuffer())
        
        extract_path = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_path, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)
        
        # 압축 해제된 폴더 찾기
        folder_name = uploaded_file.name[:uploaded_file.name.rfind('.')]
        target_path = os.path.join(extract_path, folder_name)
        print('------------------ 현재 target_path: ', target_path , '------------------')
        print('------------------ 현재 folder_name: ', folder_name , '------------------')
        
        if not os.path.isdir(target_path):
            raise FileNotFoundError(f"압축 해제된 폴더를 찾을 수 없습니다: {target_path}")
        
        logger.info(f"압축 해제 완료: {target_path}")
        
        # 2. API를 통한 수행회차 조회
        order_num = APIClient.fetch_order_num(patient_id)
        logger.info(f"수행회차: {order_num}")
        
        # 3. CSV 파일 처리 : 의뢰인, 검사일자, 검사자
        csv_file_path = os.path.join(target_path, f"{patient_id}.csv")
        
        if os.path.exists(csv_file_path):
            csv_data = parse_csv_file(csv_file_path)
            if not APIClient.save_patient_assessment(patient_id, order_num, csv_data):
                raise Exception("환자 검사 정보 저장 실패")
        else:
            logger.warning(f"CSV 파일 없음 - patient_info에서 기본 정보 조회: {patient_id}")
            patient_info = APIClient.get_patient_info(patient_id)
            if not patient_info:
                raise Exception("환자 기본 정보를 찾을 수 없습니다 (patient_info)")
            # patient_info 필드 매핑
            csv_data = {
                'age': patient_info.get('age'),
                'sex': patient_info.get('sex'),
                'edu': patient_info.get('edu'),
                'excluded': patient_info.get('excluded', '0') or '0',
                'post_stroke_date': patient_info.get('post_stroke_date'),
                'diagnosis': patient_info.get('diagnosis'),
                'stroke_type': patient_info.get('stroke_type'),
                'lesion_location': patient_info.get('lesion_location'),
                'hemiplegia': patient_info.get('hemiplegia'),
                'hemineglect': patient_info.get('hemineglect'),
                'visual_field_defect': patient_info.get('visual_field_defect'),
                # assess_lst에 필요한 필드 중 patient_info에 없는 값들은 None으로 둔다.
                'request_org': None,
                'assess_date': None,
                'assess_person': None,
                'diagnosis_etc': None,
            }
            if not APIClient.save_patient_assessment(patient_id, order_num, csv_data):
                raise Exception("환자 검사 정보 저장 실패 (patient_info 기반)")
        
        # 4. 오디오 파일 수집
        files_data = process_wav_files(target_path, patient_id, order_num)
        
        if not files_data:
            raise Exception("처리할 오디오 파일이 없습니다")
        
        logger.info(f"수집된 파일: {len(files_data)}건")
        
        # 5. 파일 변환 및 일괄 업로드
        converted_files = []  # 변환된 임시 파일 추적
        
        try:
            upload_data = []
            for item in files_data:
                file_path = item['file_path']
                
                # m4a면 wav로 변환
                if item['needs_conversion']:
                    logger.info(f"파일 변환 중: {item['original_filename']}")
                    converted_path = convert_to_wav(file_path)
                    converted_files.append(converted_path)
                    upload_path = converted_path
                else:
                    upload_path = file_path
                
                upload_data.append({
                    'file_path': upload_path,
                    'metadata': item['metadata']
                })
            
            # API를 통해 업로드
            upload_ok, api_key = APIClient.upload_files_bulk(upload_data)
            if not upload_ok:
                raise Exception("파일 업로드 실패")
            # 응답에 api_key가 없거나 비어 있으면 DB 조회/발급하여 보정
            if not api_key:
                api_key = APIClient.get_api_key_by_patient(patient_id)
            
        finally:
            # 변환된 임시 파일 정리
            for temp_file in converted_files:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                        logger.debug(f"임시 파일 삭제: {temp_file}")
                except Exception as e:
                    logger.warning(f"임시 파일 삭제 실패: {temp_file}, {e}")
        
        # 6. 중복 파일 처리
        if not APIClient.handle_duplicate_files(patient_id, order_num, api_key):
            raise Exception("중복 파일 처리 실패")
        
        # 7. 점수 테이블 초기화
        if not APIClient.initialize_scores(patient_id, order_num, api_key):
            raise Exception("점수 테이블 초기화 실패")
        
        # 8. 파일 정보 DataFrame 생성 (메타데이터만)
        df = pd.DataFrame([item['metadata'] for item in files_data])
        
        logger.info(f"[COMPLETE] ZIP 업로드 완료: {patient_id} - 회차 {order_num}")
        return str(order_num), df, api_key
        
    except Exception as e:
        logger.error(f"[ERROR] ZIP 업로드 실패: {str(e)}")
        # DB 롤백 시도
        if order_num is not None:
            APIClient.cleanup_assessment(patient_id, order_num, api_key if 'api_key' in locals() else None)
        st.error(f"업로드 중 오류 발생: {str(e)}")
        return None, None, None
    finally:
        # 임시 폴더 정리
        try:
            shutil.rmtree(temp_dir)
            logger.info("임시 폴더 정리 완료")
        except Exception as e:
            logger.warning(f"임시 폴더 정리 실패: {e}")

    
