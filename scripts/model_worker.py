import os
import sys
import time
import logging
from pathlib import Path

# 프로젝트 루트 경로 설정
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "ui"))
sys.path.append(str(ROOT))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _ensure_conda_env():
    """
    conda 환경(CLAP_PC)이 활성화되어 있지 않으면
    해당 환경의 python으로 이 스크립트를 재실행한다.
    이미 활성화 상태면 아무것도 하지 않고 반환.
    """
    from ui.utils.env_utils import find_conda_base, create_environment, ENV_NAME, WINOS

    if ENV_NAME.lower() in sys.executable.lower():
        logger.info(f"✅ {ENV_NAME} conda 환경 활성화 상태")
        return

    logger.info(f"{ENV_NAME} 환경이 아닙니다. conda 환경에서 재실행합니다...")
    conda_base = find_conda_base()
    if not conda_base:
        logger.error("❌ conda가 설치되어 있지 않습니다.")
        sys.exit(1)

    if WINOS:
        conda_python = os.path.join(conda_base, "envs", ENV_NAME, "Scripts", "python.exe")
    else:
        conda_python = os.path.join(conda_base, "envs", ENV_NAME, "bin", "python")

    if not os.path.exists(conda_python):
        logger.info(f"{ENV_NAME} 환경이 없습니다. 생성합니다...")
        if not create_environment():
            logger.error("환경 생성 실패")
            sys.exit(1)

    # conda python으로 이 스크립트를 재실행
    os.execv(conda_python, [conda_python] + sys.argv)
    # execv는 반환하지 않음


def _cleanup_conda_env():
    """
    모델링 완료 후 conda 환경 삭제.
    현재 프로세스가 해당 환경에서 실행 중이므로,
    base python으로 별도 프로세스를 띄워서 삭제한다.
    """
    import subprocess
    from ui.utils.env_utils import find_conda_base, ENV_NAME, WINOS

    logger.info(f"모든 모델링 완료. {ENV_NAME} conda 환경을 삭제합니다...")

    conda_base = find_conda_base()
    if not conda_base:
        logger.error("conda를 찾을 수 없어 환경 삭제를 건너뜁니다.")
        return

    if WINOS:
        base_python = os.path.join(conda_base, "python.exe")
        conda_cmd = os.path.join(conda_base, "Scripts", "conda.exe")
    else:
        base_python = os.path.join(conda_base, "bin", "python")
        conda_cmd = os.path.join(conda_base, "bin", "conda")

    # ToS 자동 수락 후 conda env remove 실행
    tos_script = (
        f"import subprocess; "
        f"subprocess.run(['{conda_cmd}', 'tos', 'accept', '--override-channels', '--channel', 'https://repo.anaconda.com/pkgs/main'], capture_output=True); "
        f"subprocess.run(['{conda_cmd}', 'tos', 'accept', '--override-channels', '--channel', 'https://repo.anaconda.com/pkgs/r'], capture_output=True); "
        f"subprocess.run(['{conda_cmd}', 'env', 'remove', '-n', '{ENV_NAME}', '-y'], check=True)"
    )
    try:
        subprocess.run([base_python, "-c", tos_script], check=True)
        logger.info(f"{ENV_NAME} 환경 삭제 완료")
    except subprocess.CalledProcessError:
        # conda ToS 미동의 등으로 실패 시, 환경 디렉터리 직접 삭제
        import shutil
        env_dir = os.path.join(conda_base, "envs", ENV_NAME)
        if os.path.isdir(env_dir):
            logger.warning(f"conda env remove 실패. 디렉터리 직접 삭제: {env_dir}")
            shutil.rmtree(env_dir, ignore_errors=True)
            logger.info(f"{ENV_NAME} 환경 디렉터리 삭제 완료")
        else:
            logger.error(f"환경 디렉터리가 존재하지 않습니다: {env_dir}")


def _init_heavy_imports():
    """conda 환경 확인 후 heavy 모듈들을 import"""
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ROOT / ".env", override=True)

    import pandas as pd
    from sqlalchemy import text
    from api.database import SessionLocal
    from ui.services.api_client import APIClient
    from ui.services.model_service import model_process
    from ui.services.db_service import save_scores_to_db

    return pd, text, SessionLocal, APIClient, model_process, save_scores_to_db


def get_pending_jobs(db, text):
    """파일이 존재하는 건 중 점수가 없는 회차만 조회"""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT lst.PATIENT_ID, lst.ORDER_NUM, pk.API_KEY
            FROM AUDIO_STORAGE lst
            JOIN API_KEY pk
                on pk.PATIENT_ID = lst.PATIENT_ID
            WHERE lst.USE_TF = 0
            """
        )
    ).fetchall()
    return rows


def fetch_bundle_as_path_info(patient_id: str, order_num: int, api_base_url: str, pd):
    """
    /reports/{patient_id}/{order_num}/bundle 을 호출해서
    - manifest.json → DataFrame
    - audio 파일 → 임시 디렉터리에 풀고,
    - model_process가 기대하는 컬럼 이름으로 정리하여 반환
    """
    import tarfile
    import requests
    import tempfile
    import json

    url = f"{api_base_url}/reports/{patient_id}/{order_num}/bundle"
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()

    # tar.gz 임시 저장
    tmp_tar = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    for chunk in resp.iter_content(chunk_size=1024 * 1024):
        if chunk:
            tmp_tar.write(chunk)
    tmp_tar.close()

    temp_dir = tempfile.mkdtemp(prefix=f"{patient_id}_{order_num}_")
    manifest = None

    # 압축 해제
    with tarfile.open(tmp_tar.name, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "manifest.json":
                f = tar.extractfile(member)
                manifest = json.load(f)
            else:
                tar.extract(member, path=temp_dir)

    if manifest is None:
        raise ValueError("manifest.json 이 번들에 없습니다.")

    df = pd.DataFrame(manifest)

    # relative_path 를 실제 로컬 경로로 치환
    df["file"] = df["relative_path"].apply(lambda p: os.path.join(temp_dir, p))

    # model_process가 기대하는 컬럼명으로 맞추기
    df = df.rename(columns={
        "patient_id": "patient_id",
        "order_num": "order_num",
        "assess_type": "assess_type",
        "question_cd": "question_cd",
        "question_no": "question_no",
        "question_minor_no": "question_minor_no",
        "duration": "duration",
        "rate": "rate",
    })

    return df


def process_pending_jobs(pd, text, SessionLocal, APIClient, model_process, save_scores_to_db):
    db = SessionLocal()
    try:
        pending = get_pending_jobs(db, text)
        if not pending:
            logger.info("대기 중인 모델링 작업이 없습니다.")
            return

        logger.info(f"{len(pending)}건 처리 시작")
        for patient_id, order_num, api_key in pending:
            try:
                raw_base_url = APIClient._get_api_base_url()
                api_base_url = APIClient._normalize_url(raw_base_url)
                path_info = fetch_bundle_as_path_info(patient_id, order_num, api_base_url, pd)
                if path_info.empty:
                    logger.warning(f"{patient_id}/{order_num}: 파일 메타데이터 없음, 건너뜀")
                    continue
                scores, question_meta = model_process(path_info, api_key)
                success = save_scores_to_db(scores, order_num, patient_id, question_meta=question_meta)

                if success:
                    logger.info(f"{patient_id}/{order_num}: 모델링 완료 및 점수 저장")
                else:
                    logger.error(f"{patient_id}/{order_num}: 점수 저장 실패")
            except Exception as e:
                logger.error(f"{patient_id}/{order_num}: 처리 실패 - {e}")
    finally:
        db.close()


def main(loop: bool = True, interval: int = 300):
    pd, text, SessionLocal, APIClient, model_process, save_scores_to_db = _init_heavy_imports()

    if not loop:
        process_pending_jobs(pd, text, SessionLocal, APIClient, model_process, save_scores_to_db)
        return

    logger.info(f"모델 워커 시작 (주기: {interval}초)")
    while True:
        process_pending_jobs(pd, text, SessionLocal, APIClient, model_process, save_scores_to_db)
        time.sleep(interval)


if __name__ == "__main__":
    _ensure_conda_env()
    main(loop=False)
    _cleanup_conda_env()
