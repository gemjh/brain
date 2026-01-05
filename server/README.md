# Kotlin-facing API server

Run the FastAPI app with the Kotlin-friendly endpoints only:

```bash
python -m server.main
# or
HOST=0.0.0.0 PORT=8000 UVICORN_RELOAD=true python -m server.main
```

Key endpoints (all prefixed with `/api/v1`):
- `GET /kotlin/assessments/{patientId}/{orderNum}/inputs` → fetch active file metadata for modeling
- `POST /kotlin/modeling/run` with `{ "patient_id": "...", "order_num": 1, "api_key": "...", "assess_type": "CLAP_A", "save": true }` → run models and save scores
- `GET /kotlin/modeling/{patientId}/{orderNum}` → pull saved modeling results

Example curl to trigger modeling:

```bash
curl -X POST http://localhost:8000/api/v1/kotlin/modeling/run \
  -H "Content-Type: application/json" \
  -d '{"patient_id": "1001", "order_num": 1, "api_key": "YOUR_API_KEY"}'
```
