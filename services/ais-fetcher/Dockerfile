FROM python:3.12-slim

WORKDIR /app

# Minimal dependencies — no database, no Redis
RUN pip install --no-cache-dir \
    'pydantic>=2.6,<3.0' \
    'pydantic-settings>=2.2,<3.0' \
    'pyyaml>=6.0,<7.0' \
    'websockets>=12.0,<13' \
    'orjson>=3.9'

# Copy service code
COPY . .

ENV PYTHONPATH=/app

CMD ["python", "main.py"]
