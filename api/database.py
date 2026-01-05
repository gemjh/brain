from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from pathlib import Path
import importlib.util

# .env 파일 로드
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# DB URL 구성: 사용 가능한 MySQL 드라이버를 자동 선택
driver = None
try:
    importlib.import_module("mysql.connector")
    driver = "mysqlconnector"
except ImportError:
    try:
        importlib.import_module("pymysql")
        driver = "pymysql"
    except ImportError:
        raise ImportError(
            "MySQL Python 드라이버가 설치되어 있지 않습니다. "
            "mysql-connector-python 또는 PyMySQL을 설치하세요."
        )

DATABASE_URL = (
    f"mysql+{driver}://{os.getenv('db_username')}:"
    f"{os.getenv('db_password')}@{os.getenv('db_host')}:"
    f"{os.getenv('db_port', 3306)}/{os.getenv('db_database')}"
)

print(
    f"[DEBUG] Database URL: mysql+{driver}://{os.getenv('db_username')}:***@"
    f"{os.getenv('db_host')}:{os.getenv('db_port')}/{os.getenv('db_database')}"
)

engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False  # SQL 로깅 끄기
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# DB 세션 의존성
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
