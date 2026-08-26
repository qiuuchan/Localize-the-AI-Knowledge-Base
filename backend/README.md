# KB-AI Backend · v0.8.0

Host-side FastAPI wrapper around the existing PowerShell scripts. Provides HTTP/SSE endpoints for the new frontend.

## Quick start

```powershell
# From the KB-AI root directory
pwsh -File scripts/start-backend.ps1 -Port 8000
```

Then open:
- API root: http://127.0.0.1:8000/api
- OpenAPI docs: http://127.0.0.1:8000/docs

## Stop

```powershell
pwsh -File scripts/stop-backend.ps1
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api` | API info |
| GET | `/api/health` | Latest health probe result |
| GET | `/api/status` | Combined version / containers / capacity / AI status |
| GET | `/api/sessions` | List chat sessions |
| POST | `/api/sessions` | Create a session |
| GET | `/api/sessions/{id}/messages` | Messages of a session |
| POST | `/api/sessions/{id}/messages` | Save a message |
| POST | `/api/chat` | SSE chat stream (wraps `chat.ps1`) |
| POST | `/api/shutdown` | Safe eject / stop services |
| POST | `/api/boot` | SSE boot progress |

## Run integration tests

```powershell
cd <KB-AI-root>
backend/.venv/Scripts/python -m pytest tests/integration/api/test_api.py -v
```

## Notes

- The backend runs **on the host**, not inside Docker, so it can directly call the PowerShell scripts and read/write the SQLite database.
- `start-backend.ps1` creates `backend/.venv` automatically and installs dependencies from `requirements.txt`.
- The backend reads `./.env` using the same placeholder rules as `scripts/lib/load-env.ps1`.
