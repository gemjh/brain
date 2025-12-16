import time
import tempfile
import os
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


def download_file_from_db(patient_id: str, order_num: int, question_cd: str, question_no: int) -> str:
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
    load_dotenv(dotenv_path=env_path)
    API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    
    try:
        url = f"{API_BASE_URL}/assessments/{patient_id}/{order_num}/files/{question_cd}/download"
        params = {
            'question_no': question_no,
            'convert_to_wav': True  # 항상 wav로 변환하여 받기
        }
        
        response = requests.get(url, params=params, timeout=120)
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


def model_process(path_info):
    """
    모델링 프로세스 - DB blob에서 파일을 다운로드하여 처리
    
    Args:
        path_info: DataFrame with columns [PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO, FILE_NAME]
    
    Returns:
        dict: 모델링 결과 {'LTN_RPT': 10, 'GUESS_END': 5, ...}
    """
    try:
        # 같은 문항에 여러 파일이 있는 경우 question_minor_no가 가장 큰 것만 유지
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

        # 임시 파일 관리용 리스트
        temp_files = []
        
        # 파일 경로 대신 DB 조회 정보로 그룹화
        ltn_rpt_files = []
        guess_end_files = []
        say_ani_files = []
        say_obj_files = []
        talk_clean_files = []
        talk_pic_files = []
        ah_sound_files = []
        ptk_sound_files = []
        
        # path_info에서 파일 정보 추출
        for i in range(len(path_info)):
            patient_id = str(path_info.loc[i, 'patient_id'])
            order_num = int(path_info.loc[i, 'order_num'])
            assess_type = str(path_info.loc[i, 'assess_type'])
            question_cd = str(path_info.loc[i, 'question_cd'])
            question_no = int(path_info.loc[i, 'question_no'])
            
            file_info = {
                'patient_id': patient_id,
                'order_num': order_num,
                'question_cd': question_cd,
                'question_no': question_no
            }
            
            # CLAP_A
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
            
            # CLAP_D
            elif assess_type.upper() == 'CLAP_D':
                if question_cd == 'AH_SOUND':
                    ah_sound_files.append(file_info)
                elif question_cd in ['P_SOUND', 'T_SOUND', 'K_SOUND', 'PTK_SOUND']:
                    ptk_sound_files.append(file_info)
                elif question_cd == 'TALK_CLEAN':
                    talk_clean_files.append(file_info)
        
        # 결과 저장용
        fin_scores = {}
        
        # LTN_RPT 모델
        if len(ltn_rpt_files) > 0:
            start_time = time.time()
            try:
                ltn_rpt = get_ltn_rpt()
                # 파일 다운로드
                file_paths = []
                for file_info in ltn_rpt_files:
                    temp_path = download_file_from_db(**file_info)
                    file_paths.append(temp_path)
                    temp_files.append(temp_path)
                
                ltn_rpt_result = ltn_rpt.predict_score(file_paths)
                fin_scores['LTN_RPT'] = int(ltn_rpt_result)
                logger.info(f"LTN_RPT 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"LTN_RPT 모델 실행 중 오류 발생: {e}")
                fin_scores['LTN_RPT'] = 0
        
        # GUESS_END 모델
        if len(guess_end_files) > 0:
            start_time = time.time()
            try:
                guess_end = get_guess_end()
                temp = []
                for idx, file_info in enumerate(guess_end_files):
                    temp_path = download_file_from_db(**file_info)
                    temp_files.append(temp_path)
                    temp.append(guess_end.predict_guess_end_score(temp_path, idx))
                
                guess_end_result = sum(temp)
                fin_scores['GUESS_END'] = int(guess_end_result)
                logger.info(f"GUESS_END 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"GUESS_END 모델 실행 중 오류 발생: {e}")
                fin_scores['GUESS_END'] = 0
        
        # SAY_OBJ 모델
        if len(say_obj_files) > 0:
            start_time = time.time()
            try:
                say_obj = get_say_obj()
                # 6번째(rainbow), 9번째(swing) 파일 찾기
                file_paths = []
                for file_info in say_obj_files:
                    temp_path = download_file_from_db(**file_info)
                    file_paths.append(temp_path)
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
        
        # SAY_ANI 모델
        if len(say_ani_files) > 0:
            start_time = time.time()
            try:
                say_ani = get_say_ani()
                temp_path = download_file_from_db(**say_ani_files[0])
                temp_files.append(temp_path)
                
                say_ani_result = say_ani.score_audio(temp_path)
                fin_scores['SAY_ANI'] = int(say_ani_result)
                logger.info(f"SAY_ANI 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"SAY_ANI 모델 실행 중 오류 발생: {e}")
                fin_scores['SAY_ANI'] = 0
        
        # TALK_PIC 모델
        if len(talk_pic_files) > 0:
            start_time = time.time()
            try:
                talk_pic = get_talk_pic()
                temp_path = download_file_from_db(**talk_pic_files[0])
                temp_files.append(temp_path)
                
                talk_pic_result = talk_pic.score_audio(temp_path)
                fin_scores['TALK_PIC'] = int(talk_pic_result)
                logger.info(f"TALK_PIC 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"TALK_PIC 모델 실행 중 오류 발생: {e}")
                fin_scores['TALK_PIC'] = 0
        
        # AH_SOUND 모델
        if len(ah_sound_files) > 0:
            start_time = time.time()
            try:
                ah_sound = get_ah_sound()
                temp_path = download_file_from_db(**ah_sound_files[0])
                temp_files.append(temp_path)
                
                ah_sound_result = round(ah_sound.analyze_pitch_stability(temp_path), 2)
                fin_scores['AH_SOUND'] = ah_sound_result
                logger.info(f"AH_SOUND 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"AH_SOUND 모델 실행 중 오류 발생: {e}")
                fin_scores['AH_SOUND'] = 0
        
        # PTK_SOUND 모델
        if len(ptk_sound_files) > 0:
            start_time = time.time()
            try:
                ptk_sound = get_ptk_sound()
                temp_p, temp_t, temp_k, temp_ptk = [], [], [], []
                
                file_paths = []
                for file_info in ptk_sound_files:
                    temp_path = download_file_from_db(**file_info)
                    file_paths.append(temp_path)
                    temp_files.append(temp_path)
                
                for i, path in enumerate(file_paths):
                    if i < 3:
                        temp_p.append(ptk_sound.ptk_each(path))
                    elif i < 6:
                        temp_t.append(ptk_sound.ptk_each(path))
                    elif i < 9:
                        temp_k.append(ptk_sound.ptk_each(path))
                    elif i < 12:
                        temp_ptk.append(ptk_sound.ptk_whole(path))
                
                if temp_p:
                    fin_scores['P_SOUND'] = str(round(max(temp_p), 2))
                if temp_t:
                    fin_scores['T_SOUND'] = str(round(max(temp_t), 2))
                if temp_k:
                    fin_scores['K_SOUND'] = str(round(max(temp_k), 2))
                if temp_ptk:
                    fin_scores['PTK_SOUND'] = str(round(max(temp_ptk), 2))
                    
                logger.info(f"PTK_SOUND 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"PTK_SOUND 모델 실행 중 오류 발생: {e}")
                fin_scores['P_SOUND'] = 0
                fin_scores['T_SOUND'] = 0
                fin_scores['K_SOUND'] = 0
                fin_scores['PTK_SOUND'] = 0
        
        # TALK_CLEAN 모델
        if len(talk_clean_files) > 0:
            start_time = time.time()
            try:
                talk_clean = get_talk_clean()
                file_items = []
                for file_info in talk_clean_files:
                    temp_path = download_file_from_db(**file_info)
                    file_items.append({
                        "path": temp_path,
                        "question_no": file_info['question_no']
                    })
                    temp_files.append(temp_path)
                
                talk_clean_result = talk_clean.main(file_items)
                fin_scores['TALK_CLEAN'] = int(talk_clean_result)
                logger.info(f"TALK_CLEAN 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"TALK_CLEAN 모델 실행 중 오류 발생: {e}")
                fin_scores['TALK_CLEAN'] = 0
        
        return fin_scores
    
    except Exception as e:
        logger.error(f"모델링 중 오류 발생: {e}")
        raise
    finally:
        # 임시 파일 정리
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                logger.warning(f"임시 파일 삭제 실패: {temp_file}, {e}")
