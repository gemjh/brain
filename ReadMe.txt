1. PC에서 streamlit 실행 후 로컬주소 확인
2. PC에서 API 클라우드 연결(uvicorn api.main.app --host 0.0.0.0 --port 8000 또는  python -m uvicorn api.main:app --reload)
3. 1에서 확인한 로컬주소 클라우드에 연결(uvicorn)
4. 3에서 받은 url 접속(태블릿 가능)
