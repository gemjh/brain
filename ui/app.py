import streamlit as st
# 페이지 설정
st.set_page_config(
    page_title="CLAP",
    page_icon="👋",
    layout="wide",
    initial_sidebar_state="expanded"
)
import os
import logging
import threading
import time
from typing import Optional
# TensorFlow 설정 (import 전에 먼저 설정)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TF_NUM_INTEROP_THREADS'] = '1'
os.environ['TF_NUM_INTRAOP_THREADS'] = '1'
# PyTorch MPS 호환성 문제 해결
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.0"
os.environ["CUDA_VISIBLE_DEVICES"] = ""
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ui.utils.env_utils import activate_conda_environment
from scripts.model_worker import process_pending_jobs


spinner = st.spinner('환경 설정 중...')
spinner.__enter__()
activate_conda_environment()
try:
    # 백그라운드 모델 워커 (5분 주기) 한 번만 시작
    if 'worker_thread_started' not in st.session_state:
        def _worker_loop():
            while True:
                try:
                    process_pending_jobs()
                except Exception as e:
                    logging.error(f"모델 워커 오류: {e}")
                time.sleep(300)  # 5분
        t = threading.Thread(target=_worker_loop, daemon=True)
        t.start()
        st.session_state.worker_thread_started = True

    # MPS 완전 비활성화
    import torch
    torch.backends.mps.is_available = lambda: False
    torch.backends.mps.is_built = lambda: False

    # torch.isin을 CPU로 강제하는 패치
    original_isin = torch.isin
    def patched_isin(elements, test_elements, **kwargs):
        # MPS 텐서를 CPU로 이동
        if hasattr(elements, 'device') and str(elements.device).startswith('mps'):
            elements = elements.cpu()
        if hasattr(test_elements, 'device') and str(test_elements.device).startswith('mps'):
            test_elements = test_elements.cpu()
        return original_isin(elements, test_elements, **kwargs)
    torch.isin = patched_isin
    # try:
    from tqdm import tqdm # 진행률 알려주는 라이브러리
    from ui.views.login_view import show_login_page
    from ui.views.report_view import show_main_interface
    import pandas as pd
    import plotly.express as px
    import streamlit.components.v1 as components
    import tempfile
    import os
    import zipfile
    import shutil
    import numpy as np
    import librosa
    import torch
    from ui.services.model_service import model_process


    # GPU 실행 시 tensorflow 설치 오류 방지
    try:
        import tensorflow as tf
    except Exception as e:
        print(f"TensorFlow 로드 실패, CPU 전용으로 fallback: {e}")
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'false'
        import tensorflow as tf
        tf.config.set_visible_devices([], 'GPU')

    # 운영체제 
    from pathlib import Path
    if sys.platform.startswith('win'):
        WINOS=True
        print("현재 운영체제는 윈도우입니다.")
    else: WINOS = False

    from services.db_service import (
        get_reports
    )
    from services.api_client import APIClient
    from utils.style_utils import (
        apply_custom_css
    )

    from services.auth_service import authenticate_user

    from services.upload_service import zip_upload
    apply_custom_css()

except ImportError as e:
    spinner.__exit__(None, None, None)
    st.warning("일시적인 오류가 발생했습니다. 페이지를 새로고침해 주세요")
    print(e)
    st.session_state.clear()
    st.stop()

spinner.__exit__(None, None, None)


def fetch_existing_path_info(patient_id: str, api_key: Optional[str] = None):
    """기존 업로드 데이터의 파일 정보를 DB에서 조회"""
    try:
        assessments = APIClient.get_assessments(patient_id, api_key=api_key)
        if not assessments:
            return None, None
        
        latest = max(
            assessments,
            key=lambda item: int(item.get('order_num', 0) or 0)
        )
        order_num = latest.get('order_num')
        if not order_num:
            return None, None
        
        files = APIClient.get_assessment_files(patient_id, int(order_num), api_key=api_key)
        if not files:
            return None, None
        
        path_info = pd.DataFrame(files)
        path_info.columns = [col.upper() for col in path_info.columns]
        return int(order_num), path_info
    except Exception as e:
        logging.error(f"기존 파일 정보 조회 실패: {e}")
        return None, None


def main():
    btn_apply =False

    # 테스트용(주석해제 시 파일업로드 패스)
    # st.session_state.upload_completed=True
    # patient_id=1001
    # st.session_state.patient_id=patient_id
    # path_info=[]
    # st.session_state.path_info=path_info
    # uploaded_file=[]

    # 세션 상태 초기화
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user_info = None
        st.session_state.current_page = "리포트"
        st.session_state.view_mode = "list"
        st.session_state.upload_completed=False
        st.session_state.api_key = None
        st.session_state.order_num = None

    # 첫화면: 로그인화면 / 환자정보등록화면
    if not st.session_state.logged_in:
        show_login_page()
    # 파일이 등록된 경우
    elif st.session_state.upload_completed:
        if st.session_state.get('api_key'):
            st.info(f"이 세션의 API Key: `{st.session_state.api_key}`")
        # 리포트 메인 이동
        show_main_interface(st.session_state.patient_id,st.session_state.path_info) 
    # 파일이 등록되지 않은 경우
    else:
        # UI 플레이스홀더 생성
        # ui_placeholder = st.empty()
        
        # with ui_placeholder.container():
            BASE_DIR = Path(__file__).parent
            patient_csv = BASE_DIR / "patient_id.csv"
            patient_id = st.selectbox("환자ID를 입력하세요.",pd.read_csv(patient_csv)['patient_id'].tolist())
            patient_id=str(patient_id)
            st.session_state.patient_id=patient_id

            uploaded_file = st.file_uploader("폴더를 압축(zip)한 파일을 업로드하세요.", type=['zip'])
            # if st.session_state.get("api_key"):
            #     st.info(f"현재 세션 API Key: `{st.session_state.api_key}`")
            api_key_input = st.text_input("이미 발급받은 API Key가 있다면 입력하세요 (업로드 스킵용)", value=st.session_state.get('api_key') or "")
            skip_upload = st.button("업로드 스킵", key="skip_btn")
            if skip_upload:
                if api_key_input:
                    try:
                        resolved = APIClient.resolve_api_key(api_key_input)
                        patient_id_resolved = resolved.get("patient_id")
                        if patient_id_resolved and patient_id_resolved != patient_id:
                            st.warning("입력한 환자ID와 API Key가 매핑된 환자ID가 다릅니다. 올바른 조합인지 확인하세요.")
                            st.stop()
                        st.session_state.patient_id = patient_id_resolved
                        st.session_state.api_key = api_key_input
                        order_num, path_info = fetch_existing_path_info(patient_id_resolved, api_key=api_key_input)
                        if path_info is None or path_info.empty:
                            st.warning("DB에서 파일 정보를 찾을 수 없습니다.")
                        else:
                            st.session_state.path_info = path_info
                            st.session_state.order_num = order_num
                            st.session_state.upload_completed = True
                            st.rerun()
                    except Exception as e:
                        st.warning(f"API Key 확인 실패: {e}")
                else:
                    st.warning("API Key를 입력하세요.")
            col1, col2 = st.columns([2.5, 7.5])
            with col1:
                # zip파일이 등록되면 파일 업로드 버튼 보임
                if uploaded_file is not None:
                    btn_apply = st.button("파일 업로드", key="upload_btn")
                    
    if btn_apply:
        st.session_state.path_info=loading(btn_apply,patient_id,uploaded_file)
        st.session_state.upload_completed=True
        st.rerun()

def loading(btn_apply,patient_id,uploaded_file):
    # ------------- zip파일 처리 -----------------
    order_num,path_info,api_key=zip_upload(btn_apply,patient_id,uploaded_file)
    if path_info is None or order_num is None:
        st.error("업로드 중 오류가 발생했습니다. 로그를 확인하세요.")
        return None
    st.session_state.order_num = order_num
    st.session_state.api_key = api_key

    # 업로드/저장까지 완료된 시점에 바로 알림 표시
    if st.session_state.api_key:
        st.info(f"파일을 업로드했습니다. access key: `{st.session_state.api_key}`")
    else:
        st.info("파일을 업로드했습니다.")

    # ------------- 모델링 및 저장: 별도 스레드로 처리하여 UI를 바로 반환 -------------
    def _run_modeling():
        try:
            fin_scores = model_process(path_info, api_key)
            from services.db_service import save_scores_to_db
            save_scores_to_db(fin_scores, order_num, patient_id)
            logging.info("모델링 및 점수 저장 완료")
        except Exception as e:
            logging.error(f"모델링/점수 저장 중 오류: {e}")

    threading.Thread(target=_run_modeling, daemon=True).start()
    return path_info
    

if __name__ == "__main__":
    main()
