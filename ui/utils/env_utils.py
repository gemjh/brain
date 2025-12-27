#!/usr/bin/env python3
"""
SPICE 기반 단일음정 유지 능력 평가 코드 (.py 버전)
노트북에서 Python 스크립트로 변환 - 자동 conda 환경 활성화
TensorFlow Metal 오류 해결 버전
"""
import os
import subprocess
import sys
import shutil
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

WINOS = sys.platform.startswith('win')

def model_common_path():
    """
    Return path to models folder, falling back to repository root if .env or python-dotenv are missing.
    """
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"

    if load_dotenv and env_path.exists():
        load_dotenv(dotenv_path=env_path)
        base_path = os.getenv("base_path")
        if base_path:
            return os.path.join(base_path, "models")

    return os.path.join(repo_root.as_posix(), "models")

# TensorFlow 설정 (import 전에 설정)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TF_NUM_INTEROP_THREADS'] = '1'
os.environ['TF_NUM_INTRAOP_THREADS'] = '1'

ENV_NAME = "CLAP_PC"

def find_environment_file():
    """
    Locate environment.yaml starting from repository root up the tree.
    """
    candidates = [
        Path(__file__).resolve().parents[2] / "environment.yaml",
        Path.cwd() / "environment.yaml"
    ]
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "environment.yaml")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None

def find_conda_base():
    """conda 설치 경로 찾기"""
    if WINOS:
        win_conda_paths = [
            os.path.expanduser("~\\anaconda3"),
            os.path.expanduser("~\\miniconda3"),
            "C:\\Users\\user\\anaconda3",
            "C:\\ProgramData\\Anaconda3",
            "C:\\ProgramData\\Miniconda3"
        ]
        for conda_base in win_conda_paths:
            if os.path.exists(os.path.join(conda_base, "Scripts", "conda.exe")):
                return conda_base
        return None
    possible_conda_paths = [
        os.path.expanduser("~/opt/anaconda3"),
        os.path.expanduser("~/miniconda3"), 
        os.path.expanduser("~/anaconda3"),
        "/opt/anaconda3",
        "/opt/miniconda3"
    ]
    
    for conda_base in possible_conda_paths:
        if os.path.exists(os.path.join(conda_base, "bin", "conda")):
            return conda_base
    
    return None


def create_environment():
    """conda 환경 자동 생성"""
    print("환경이 없습니다. 자동으로 생성합니다...")
    env_path = find_environment_file()
    if not env_path:
        print("❌ environment.yaml 파일을 찾을 수 없습니다.")
        return False

    conda_base = find_conda_base()
    if not conda_base:
        print("❌ conda가 설치되어 있지 않습니다.")
        print("https://docs.conda.io/en/latest/miniconda.html 에서 miniconda를 설치하세요.")
        return False
    
    # 패키지 캐시 디렉터리를 워크스페이스로 강제(쓰기 권한/캐시 깨짐 회피)
    repo_root = Path(__file__).resolve().parents[2]
    pkgs_dir = repo_root / ".conda_pkgs"
    if pkgs_dir.exists():
        shutil.rmtree(pkgs_dir)
    pkgs_dir.mkdir(exist_ok=True)

    condarc_path = repo_root / ".condarc.auto.yaml"
    condarc_path.write_text(f"pkgs_dirs:\n  - {pkgs_dir}\n")

    run_env = os.environ.copy()
    run_env["CONDA_PKGS_DIRS"] = str(pkgs_dir)
    run_env["CONDARC"] = str(condarc_path)
    
    try:
        print("필수 라이브러리 설치 중...")
        if WINOS:
            conda_cmd = os.path.join(conda_base, "Scripts", "conda.exe")
        else:
            conda_cmd = os.path.join(conda_base, "bin", "conda")
        subprocess.run(
            [conda_cmd, "env", "create", "-f", str(env_path)],
            check=True,
            env=run_env
        )
        print("생성 완료")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 환경 생성 실패: {e}")
        return False
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        return False

def activate_conda_environment():
    """conda 환경 자동 활성화 또는 생성"""
    try:
        # 현재 Python 실행 경로 확인
        current_python = sys.executable
        print(f"현재 Python 경로: {current_python}")
        
        # SeSAC 환경 경로 확인
        if ENV_NAME.lower() not in current_python.lower():
            print(f"{ENV_NAME} 환경이 아닙니다.")
            
            conda_base = find_conda_base()
            if not conda_base:
                print("❌ conda가 설치되어 있지 않습니다.")
                sys.exit(1)
            
            if WINOS:
                sesac_python = os.path.join(conda_base, "envs", ENV_NAME, "Scripts", "python.exe")
            else:
                sesac_python = os.path.join(conda_base, "envs", ENV_NAME, "bin", "python")
            
            # SeSAC 환경이 있는지 확인
            if not os.path.exists(sesac_python):
                # SeSAC 환경이 없으면 생성
                if not create_environment():
                    print("환경 생성에 실패했습니다.")
                    sys.exit(1)
            
            print(f"{ENV_NAME} 환경에서 재실행: {sesac_python}")
            # streamlit 앱을 CLAP_PC 환경에서 재실행
            app_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.py")
            subprocess.run([sesac_python, "-m", "streamlit", "run", app_path] + sys.argv[1:])
            sys.exit(0)
        else:
            print(f"✅ {ENV_NAME} 환경이 활성화되어 있습니다.")
    except Exception as e:
        print(f"환경 확인 중 오류 발생: {e}")
        sys.exit(1)

def delete_conda_environment(env_name=''):
    """conda 환경 삭제"""
    try:
        conda_base = find_conda_base()
        if WINOS:
            conda_cmd = os.path.join(conda_base, "Scripts", "conda.exe")
        else:
            conda_cmd = os.path.join(conda_base, "bin", "conda")
        subprocess.run([conda_cmd, "remove", "-n", env_name, "--all", "-y"], 
                        check=True, capture_output=True, text=True)  
        print("삭제 완료")
    except Exception as e:
        print(f"환경 삭제 중 오류 발생: {e}")
        sys.exit(1)

# 호출만 해도 conda 환경 자동 활성화 실행
# activate_conda_environment()
