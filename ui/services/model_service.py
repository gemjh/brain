import time
import os
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


def model_process(path_info, api_key=None):
    """
    모델링 프로세스 - DB blob에서 파일을 다운로드하여 처리
    
    Args:
        path_info: DataFrame with columns [PATIENT_ID, ORDER_NUM, ASSESS_TYPE, QUESTION_CD, QUESTION_NO, QUESTION_MINOR_NO, SCORE, USE_TF, DURATION, RATE, FILE]
    
    Returns:
        dict: 모델링 결과 {'LTN_RPT': 10, 'GUESS_END': 5, ...}
    """
    temp_files = []
    # minor_no이 제일 큰 파일 1개만 분석하고 싶으면
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
            question_minor_no = int(path_info.loc[i, 'question_minor_no'])

            file_info = {
                'patient_id': patient_id,
                'order_num': order_num,
                'assess_type': assess_type,
                'question_cd': question_cd,
                'question_no': question_no,
                'question_minor_no': question_minor_no if 'question_minor_no' in path_info.columns else 0,
                'file': path_info.loc[i, 'file'] if 'file' in path_info.columns else None,
                'score': path_info.loc[i, 'score'] if 'score' in path_info.columns else None,
            }
            # question_cd 명명규칙 변경
            name={
                'D1':'AH_SOUND',
                'D2':'PTK_BULK',
                'D3':'TALK_CLEAN',
                'D4':'READ_CLEAN',
                'CODE4':'LTN_RPT',
                'CODE5':'GUESS_END',
                'CODE6':'SAY_OBJ',
                'CODE7':'SAY_ANI',
                'CODE8':'TALK_PIC'
            }
            question_cd = name[question_cd]

            if assess_type.upper() == 'CLAP-A':
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
            elif assess_type.upper() == 'CLAP-D':
                if question_cd == 'AH_SOUND':
                    ah_sound_files.append(file_info)
                elif question_cd == 'PTK_BULK':
                    ptk_sound_files.append(file_info)
                elif question_cd == 'TALK_CLEAN':
                    talk_clean_files.append(file_info)
        
        # fin_scores = {}
        scored_file_infos = [] # api 전송할 전체 점수 목록(bulk)
        
        def resolve_audio_path(file_info):
            local_path = file_info.get("file")
            if local_path and os.path.exists(local_path):
                # 번들에서 뽑힌 실제 wav 경로
                return local_path, False

            # content_b64 = file_info.get("file")
            # if content_b64:
            #     try:
            #         data = base64.b64decode(content_b64)
            #     except Exception as e:
            #         raise ValueError(f"file_content 디코딩 실패: {e}")
            #     temp_file = tempfile.NamedTemporaryFile(delete=False)
            #     with open(temp_file.name, "wb") as f:
            #         f.write(data)
            #     return temp_file.name, True
            # temp_path = download_file_from_db(api_key=api_key, **file_info)
            # return temp_path, True

        if len(ltn_rpt_files) > 0:
            start_time = time.time()
            try:
                ltn_rpt = get_ltn_rpt()
                # 각 파일 호출
                file_paths = [resolve_audio_path(fi)[0] for fi in ltn_rpt_files]
                temp_files.extend([resolve_audio_path(fi)[0] for fi in ltn_rpt_files if resolve_audio_path(fi)[1]])

                ltn_rpt_result = ltn_rpt.predict_score(file_paths)

                # file_info에 모델링한 점수 추가
                for i, file_info in enumerate(ltn_rpt_files):
                    file_info['score'] = ltn_rpt_result[i]
                    scored_file_infos.append(file_info)
                logger.info(f"LTN_RPT 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"LTN_RPT 모델 실행 중 오류 발생: {e}")
                raise
        
        if len(guess_end_files) > 0:
            start_time = time.time()
            try:
                guess_end = get_guess_end()
                for idx, file_info in enumerate(guess_end_files):
                    temp_path, should_cleanup = resolve_audio_path(file_info)
                    if should_cleanup:
                        temp_files.append(temp_path)
                    # 한 번의 순회에서 점수 계산 + 할당
                    file_info['score'] = int(guess_end.predict_guess_end_score(temp_path, idx))
                    scored_file_infos.append(file_info)
                logger.info(f"GUESS_END 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"GUESS_END 모델 실행 중 오류 발생: {e}")
                raise
        
        # say_obj : 입력 9개 중 6번(무지개), 9번(그네)만 사용 → 총점 1개 반환
        # 대표 행(무지개, index=5)에 총점 저장, 나머지는 SCORE=NULL로 USE_TF만 1 처리
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

                say_obj_score = None
                if len(file_paths) >= 9:
                    say_obj_score = round(say_obj.predict_say_object_total(file_paths[5], file_paths[8]), 2)

                for i, file_info in enumerate(say_obj_files):
                    if i == 5 and say_obj_score is not None:
                        file_info['score'] = say_obj_score
                    else:
                        file_info['score'] = None
                    scored_file_infos.append(file_info)

                logger.info(f"SAY_OBJ 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"SAY_OBJ 모델 실행 중 오류 발생: {e}")
                raise
        
        if len(say_ani_files) > 0:
            start_time = time.time()
            try:
                say_ani = get_say_ani()
                for file_info in say_ani_files:
                    temp_path, should_cleanup = resolve_audio_path(file_info)
                    if should_cleanup:
                        temp_files.append(temp_path)
                    # 한 번의 순회에서 점수 계산 + 할당
                    file_info['score'] = int(say_ani.score_audio(temp_path))
                    scored_file_infos.append(file_info)
                logger.info(f"SAY_ANI 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"SAY_ANI 모델 실행 중 오류 발생: {e}")
                raise
                
        if len(talk_pic_files) > 0:
            start_time = time.time()
            try:
                talk_pic = get_talk_pic()
                for file_info in talk_pic_files:
                    temp_path, should_cleanup = resolve_audio_path(file_info)
                    if should_cleanup:
                        temp_files.append(temp_path)
                    # 한 번의 순회에서 점수 계산 + 할당
                    file_info['score'] = int(talk_pic.score_audio(temp_path))
                    scored_file_infos.append(file_info)
                logger.info(f"TALK_PIC 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"TALK_PIC 모델 실행 중 오류 발생: {e}")
                raise
                        
        if len(ah_sound_files) > 0:
            start_time = time.time()
            try:
                ah_sound = get_ah_sound()
                file_info = ah_sound_files[0]
                temp_path, should_cleanup = resolve_audio_path(file_info)
                if should_cleanup:
                    temp_files.append(temp_path)
                # 점수 계산 + 할당
                file_info['score'] = round(ah_sound.analyze_pitch_stability(temp_path), 2)
                scored_file_infos.append(file_info)
                logger.info(f"AH_SOUND 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"AH_SOUND 모델 실행 중 오류 발생: {e}")
        
        if len(ptk_sound_files) > 0:
            start_time = time.time()
            try:
                ptk_sound = get_ptk_sound()                
                file_paths = []
                for ptk_file in ptk_sound_files:
                    temp_path, should_cleanup = resolve_audio_path(ptk_file)
                    file_paths.append(temp_path)
                    if should_cleanup:
                        temp_files.append(temp_path)
                
                for i, path in enumerate(file_paths):
                    file_info = ptk_sound_files[i]  # 각 파일의 정보 사용
                    if i >= 9:
                        file_info['score'] = round(ptk_sound.ptk_whole(path), 2)
                    else:
                        file_info['score'] = round(ptk_sound.ptk_each(path), 2)

                    scored_file_infos.append(file_info)
                    
                logger.info(f"PTK_SOUND 모델 실행 시간: {time.time() - start_time:.2f}초")
                
            except Exception as e:
                logger.error(f"PTK_SOUND 모델 실행 중 오류 발생: {e}")
                raise
        
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
                
                # 모델 실행 후, 결과를 각 file_info에 할당 (한 번만 순회)
                for i, file_info in enumerate(talk_clean_files):
                    file_info['score'] = talk_clean_result[i]
                    scored_file_infos.append(file_info)
                logger.info(f"TALK_CLEAN 모델 실행 시간: {time.time() - start_time:.2f}초")
            except Exception as e:
                logger.error(f"TALK_CLEAN 모델 실행 중 오류 발생: {e}")
                raise
        
        return scored_file_infos, path_info
    
    except Exception as e:
        logger.error(f"모델링 중 오류 발생: {e}")
        raise
    finally:
        # 임시 파일 삭제
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                logger.warning(f"임시 파일 삭제 실패: {temp_file}, {e}")
