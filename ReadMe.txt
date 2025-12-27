1. PC에서 API 연결(uvicorn api.main.app --host 0.0.0.0 --port 8000 또는  python -m uvicorn api.main:app --reload)
2. 1의 url 클라우드 연결(cloudflared tunnel --url http://localhost:8000/)
3. config에서 api 주소 갱신하고 PC에서 streamlit 실행
4. 3에서 확인한 로컬주소 클라우드에 연결(cloudflared tunnel --url http://localhost:8501/)
5. 4에서 받은 url 접속
