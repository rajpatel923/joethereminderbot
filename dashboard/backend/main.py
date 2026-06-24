import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader

from dashboard.backend.routes import reminders, notes, history, users

API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=False)


def _verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    expected = os.environ.get("DASHBOARD_API_KEY", "")
    if not expected:
        return  # No key configured — open access (dev mode)
    token = api_key or ""
    if token.startswith("Bearer "):
        token = token[7:]
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")


app = FastAPI(title="PersonalReminderAgent Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DASHBOARD_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reminders.router, dependencies=[Depends(_verify_api_key)])
app.include_router(notes.router, dependencies=[Depends(_verify_api_key)])
app.include_router(history.router, dependencies=[Depends(_verify_api_key)])
app.include_router(users.router, dependencies=[Depends(_verify_api_key)])


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
