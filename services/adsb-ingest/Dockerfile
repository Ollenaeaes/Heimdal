FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install shared requirements inline (shared/ is a volume mount at runtime)
RUN pip install --no-cache-dir \
    'pydantic>=2.6,<3.0' \
    'pydantic-settings>=2.2,<3.0' \
    'sqlalchemy[asyncio]>=2.0,<3.0' \
    'asyncpg>=0.29,<1.0' \
    'geoalchemy2>=0.14,<1.0' \
    'redis[hiredis]>=5.0,<6.0' \
    'pyyaml>=6.0,<7.0' \
    'aiohttp>=3.9,<4.0' \
    'h3>=4.0,<5.0'

# Copy service code
COPY . .

ENV PYTHONPATH=/app

CMD ["python", "main.py"]
