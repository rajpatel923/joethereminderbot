FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 botuser

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/

# Create data directory
RUN mkdir -p /app/data && chown -R botuser:botuser /app

USER botuser

CMD ["python", "-m", "src.main"]
