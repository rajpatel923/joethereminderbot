FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# src/ is mounted via docker-compose volume at /app/src
# dashboard/backend/ files
COPY . ./dashboard/backend/

RUN mkdir -p /app/data

CMD ["uvicorn", "dashboard.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
