import time
import tempfile
import os
import json
import base64
import requests
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Lazy loading 함수들
def get_talk_pic():
    from models import talk_pic
    return talk_pic

def get_ah_sound():
    from models import ah_sound
    return ah_sound

def get_ptk_sound():
    from models import ptk_sound
    return ptk_sound

def get_talk_clean():
    from models import talk_clean
    return talk_clean

def get_say_ani():
    from models import say_ani
    return say_ani

def get_ltn_rpt():
    from models import ltn_rpt
    return ltn_rpt

def get_say_obj():
    from models import say_obj
    return say_obj

def get_guess_end():
    from models import guess_end
    return guess_end


def download_file_from_db(patient_id: str, order_num: int, question_cd: str, question_no: int, api_key: str = None) -> str:
    """
    DB에서 blob 파일을 다운로드하여 임시 파일로 저장
    m4a 파일은 자동으로 wav로 변환됨
    
    Args:
        patient_id: 환자 ID
        order_num: 검사 회차
        question_cd: 문항 코드
        question_no: 문항 번호
    
    Returns:
        str: 임시 wav 파일 경로
    """
    from dotenv import load_dotenv
    from pathlib import Path as EnvPath
    
    env_path = EnvPath(__file__).parent.parent.parent / ".env"
    config_path = EnvPath(__file__).resolve().parents[2] / "config" / "api_base.json"
    load_dotenv(dotenv_path=env_path)

    def _get_api_base_url() -> str:
        # 1순위: .env / 환경 변수
        env_url = os.getenv("API_BASE_URL", "").strip()
        if env_url:
            return env_url

        # 2순위: config/api_base.json
        try:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    url = str(data.get("api_base_url", "")).strip()
                    if url:
                        return url
        except Exception as e:
            logger.warning(f"api_base.json 로드 실패, .env 사용: {e}")

        # 3순위: 기본값
        return "http://localhost:8000/api/v1"

    def _normalize_url(url: str) -> str:
        url = url.strip()
        if not url:
            return url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"http://{url}"

    API_BASE_URL = _normalize_url(_get_api_base_url())
    
    try:
        url = f"{API_BASE_URL}/assessments/{patient_id}/{order_num}/files/{question_cd}/download"
        params = {
            'question_no': question_no,
            'convert_to_wav': True  # 항상 wav로 변환하여 받기
        }
        
        headers = {"X-API-KEY": api_key} if api_key else None
        response = requests.get(url, params=params, headers=headers, timeout=120)
        response.raise_for_status()
        
        # 임시 파일 생성 (항상 .wav)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        temp_file.write(response.content)
        temp_file.close()
        
        logger.info(f"파일 다운로드 완료: {patient_id}/{order_num}/{question_cd}/{question_no}")
        return temp_file.name
    except Exception as e:
        logger.error(f"파일 다운로드 실패: {e}")
        raise


def model_process(path_info, api_key=None):
    """
    모델링 프로세스 - DB blob에서 파일을 다운로드하여 처리
    
    Args:
        path_info: DataFrame with columns [PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO, FILE_NAME]
    
    Returns:
        dict: 모델링 결과 {'LTN_RPT': 10, 'GUESS_END': 5, ...}
    """
    temp_files = []
    try:
        group_cols = ['patient_id', 'order_num', 'assess_type', 'question_cd', 'question_no']
        if 'question_minor_no' in path_info.columns:
            try:
                path_info['question_minor_no'] = path_info['question_minor_no'].astype(int)
            except Exception:
                path_info['question_minor_no'] = pd.to_numeric(path_info['question_minor_no'], errors='coerce').fillna(0).astype(int)
            dedup_idx = path_info.groupby(group_cols)['question_minor_no'].idxmax()
            path_info = path_info.loc[dedup_idx].reset_index(drop=True)
        else:
            path_info = path_info.drop_duplicates(subset=group_cols, keep='last').reset_index(drop=True)

        ltn_rpt_files = []
        guess_end_files = []
        say_ani_files = []
        say_obj_files = []
        talk_clean_files = []
        talk_pic_files = []
        ah_sound_files = []
        ptk_sound_files = []
        
        for i in range(len(path_info)):
            patient_id = str(path_info.loc[i, 'patient_id'])
            order_num = int(path_info.loc[i, 'order_num'])
            assess_type = str(path_info.loc[i, 'assess_type'])
            question_cd = str(path_info.loc[i, 'question_cd'])
            question_no = int(path_info.loc[i, 'question_no'])
            
            file_info = {
                'patient_id': patient_id,
                'order_num': order_num,
                'assess_type': assess_type,
                'question_cd': question_cd,
                'question_no': question_no,
                'question_minor_no': int(path_info.loc[i, 'question_minor_no']) if 'question_minor_no' in path_info.columns else 0,
                'file_path': path_info.loc[i, 'file_path'] if 'file_path' in path_info.columns else None,
                'file_name': path_info.loc[i, 'file_name'] if 'file_name' in path_info.columns else None,
                'file_content': path_info.loc[i, 'file_content'] if 'file_content' in path_info.columns else None,
            }
            
            if assess_type.upper() == 'CLAP_A':
                if question_cd == 'LTN_RPT':
                    ltn_rpt_files.append(file_info)
                elif question_cd == 'GUESS_END':
                    guess_end_files.append(file_info)
                elif question_cd == 'SAY_OBJ':
                    say_obj_files.append(file_info)
                elif question_cd == 'SAY_ANI':
                    say_ani_files.append(file_info)
                elif question_cd == 'TALK_PIC':
                    talk_pic_files.append(file_info)
            elif assess_type.upper() == 'CLAP_D':
                if question_cd == 'AH_SOUND':
                    ah_sound_files.append(file_info)
                elif question_cd in ['P_SOUND', 'T_SOUND', 'K_SOUND', 'PTK_SOUND']:
                    ptk_sound_files.append(file_info)
                elif question_cd == 'TALK_CLEAN':
                    talk_clean_files.append(file_info)
        
        fin_scores = {}
        
        def resolve_audio_path(file_info):
            local_path = file_info.get("file_path")
            if local_path:
                if not os.path.exists(local_path):
                    raise FileNotFoundError(f"파일을 찾을 수 없습니다: {local_path}")
                return local_path, False
            content_b64 = file_info.get("file_content")
            if content_b64:
                try:
                    data = base64.b64decode(content_b64)
                except Exception as e:
                    raise ValueError(f"file_content 디코딩 실패: {e}")
                suffix = ""
                fname = file_info.get("file_name") or ""
                if "." in fname:
                    suffix = os.path.splitext(fname)[1]
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".wav")
                with open(temp_file.name, "wb") as f:
                    f.write(data)
                return temp_file.name, True
            temp_path = download_file_from_db(api_key=api_key, **file_info)
            return temp_path, True

        if len(ltn_rpt_files) > 0:
            start_time = time.time()
            try:
                ltn_rpt = get_ltn_rpt()
                file_paths = []
                for file_info in ltn_rpt_files:
                    temp_path, should_cleanup = resolve_audio_path(file_info)
                    file_paths.append(temp_path)
                    if should_cleanup:
                        temp_files.append(temp_path)
                
                ltn_rpt_result = ltn_rpt.predict_score(file_paths)
                fin_scores['LTN_RPT'] = ltn_rpt_result
                logger.info(f"LTN_RPT 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"LTN_RPT 모델 실행 중 오류 발생: {e}")
                raise
        
        if len(guess_end_files) > 0:
            start_time = time.time()
            try:
                guess_end = get_guess_end()
                guess_end_result = []
                for idx, file_info in enumerate(guess_end_files):
                    temp_path, should_cleanup = resolve_audio_path(file_info)
                    if should_cleanup:
                        temp_files.append(temp_path)
                    guess_end_result.append(int(guess_end.predict_guess_end_score(temp_path, idx)))
                
                fin_scores['GUESS_END'] = guess_end_result
                logger.info(f"GUESS_END 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"GUESS_END 모델 실행 중 오류 발생: {e}")
                raise
        
        # say_obj : 문항별 점수 없음, 총점만 반환
        if len(say_obj_files) > 0:
            start_time = time.time()
            try:
                say_obj = get_say_obj()
                file_paths = []
                for file_info in say_obj_files:
                    temp_path, should_cleanup = resolve_audio_path(file_info)
                    file_paths.append(temp_path)
                    if should_cleanup:
                        temp_files.append(temp_path)
                
                if len(file_paths) >= 9:
                    say_obj_result = say_obj.predict_say_object_total(file_paths[5], file_paths[8])
                    fin_scores['SAY_OBJ'] = int(say_obj_result)
                else:
                    fin_scores['SAY_OBJ'] = 0
                logger.info(f"SAY_OBJ 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"SAY_OBJ 모델 실행 중 오류 발생: {e}")
                fin_scores['SAY_OBJ'] = 0
        
        if len(say_ani_files) > 0:
            start_time = time.time()
            try:
                say_ani = get_say_ani()
                say_ani_result = []
                for i in range(len(say_ani_files)):
                    temp_path, should_cleanup = resolve_audio_path(say_ani_files[i])
                    if should_cleanup:
                        temp_files.append(temp_path)
                
                    say_ani_result.append(int(say_ani.score_audio(temp_path)))
                fin_scores['SAY_ANI'] = say_ani_result
                logger.info(f"SAY_ANI 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"SAY_ANI 모델 실행 중 오류 발생: {e}")
                raise
        
        if len(talk_pic_files) > 0:
            start_time = time.time()
            try:
                talk_pic = get_talk_pic()
                talk_pic_result = []
                for i in range(len(talk_pic_files)):
                    temp_path, should_cleanup = resolve_audio_path(talk_pic_files[i])
                    if should_cleanup:
                        temp_files.append(temp_path)
                
                    talk_pic_result.append(int(talk_pic.score_audio(temp_path)))
                fin_scores['TALK_PIC'] = talk_pic_result
                logger.info(f"TALK_PIC 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"TALK_PIC 모델 실행 중 오류 발생: {e}")
                raise
        
        if len(ah_sound_files) > 0:
            start_time = time.time()
            try:
                ah_sound = get_ah_sound()
                temp_path, should_cleanup = resolve_audio_path(ah_sound_files[0])
                if should_cleanup:
                    temp_files.append(temp_path)
                
                ah_sound_result = round(ah_sound.analyze_pitch_stability(temp_path), 2)
                fin_scores['AH_SOUND'] = ah_sound_result
                logger.info(f"AH_SOUND 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"AH_SOUND 모델 실행 중 오류 발생: {e}")
                fin_scores['AH_SOUND'] = 0
        
        if len(ptk_sound_files) > 0:
            start_time = time.time()
            try:
                ptk_sound = get_ptk_sound()
                temp_p, temp_t, temp_k, temp_ptk = [], [], [], []
                
                file_paths = []
                for file_info in ptk_sound_files:
                    temp_path, should_cleanup = resolve_audio_path(file_info)
                    file_paths.append(temp_path)
                    if should_cleanup:
                        temp_files.append(temp_path)
                
                for i, path in enumerate(file_paths):
                    if i < 3:
                        temp_p.append(round(ptk_sound.ptk_each(path),2))
                    elif i < 6:
                        temp_t.append(round(ptk_sound.ptk_each(path),2))
                    elif i < 9:
                        temp_k.append(round(ptk_sound.ptk_each(path),2))
                    elif i < 12:
                        temp_ptk.append(round(ptk_sound.ptk_whole(path),2))
                
                if temp_p:
                    fin_scores['P_SOUND'] = temp_p
                if temp_t:
                    fin_scores['T_SOUND'] = temp_t
                if temp_k:
                    fin_scores['K_SOUND'] = temp_k
                if temp_ptk:
                    fin_scores['PTK_SOUND'] = temp_ptk
                    
                logger.info(f"PTK_SOUND 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"PTK_SOUND 모델 실행 중 오류 발생: {e}")
                raise
                # fin_scores['P_SOUND'] = [0]
                # fin_scores['T_SOUND'] = [0]
                # fin_scores['K_SOUND'] = [0]
                # fin_scores['PTK_SOUND'] = [0]
        
        if len(talk_clean_files) > 0:
            start_time = time.time()
            try:
                talk_clean = get_talk_clean()
                file_items = []
                for file_info in talk_clean_files:
                    temp_path, should_cleanup = resolve_audio_path(file_info)
                    file_items.append({
                        "path": temp_path,
                        "question_no": file_info['question_no']
                    })
                    if should_cleanup:
                        temp_files.append(temp_path)
                
                talk_clean_result = talk_clean.main(file_items)
                fin_scores['TALK_CLEAN'] = talk_clean_result
                logger.info(f"TALK_CLEAN 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"TALK_CLEAN 모델 실행 중 오류 발생: {e}")
                raise
        
        return fin_scores
    
    except Exception as e:
        logger.error(f"모델링 중 오류 발생: {e}")
        raise
    finally:
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                logger.warning(f"임시 파일 삭제 실패: {temp_file}, {e}")
