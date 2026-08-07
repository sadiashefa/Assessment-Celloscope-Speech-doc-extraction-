FROM python:3.11-slim

# Create non-root user first
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

# Install dependencies as root before switching user
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Switch to non-root user — no model downloads, no secrets baked in
USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
