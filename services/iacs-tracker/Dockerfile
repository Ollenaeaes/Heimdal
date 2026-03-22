FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY iacs_tracker.py .

# Shared library mounted at runtime via docker-compose
ENV PYTHONPATH=/app

ENTRYPOINT ["python", "iacs_tracker.py"]
