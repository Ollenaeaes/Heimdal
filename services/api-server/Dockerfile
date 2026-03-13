FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements
# Note: shared/ is mounted at runtime, but we need requirements at build time
# So we copy the base requirements file first, then install service requirements
COPY requirements.txt ./requirements-service.txt

# We can't -r /app/shared/requirements-base.txt at build time since shared is a volume mount
# Instead, install shared requirements inline and service-specific ones
RUN pip install --no-cache-dir \
    'pydantic>=2.6,<3.0' \
    'pydantic-settings>=2.2,<3.0' \
    'sqlalchemy[asyncio]>=2.0,<3.0' \
    'asyncpg>=0.29,<1.0' \
    'geoalchemy2>=0.14,<1.0' \
    'redis[hiredis]>=5.0,<6.0' \
    'pyyaml>=6.0,<7.0' \
    'fastapi>=0.110,<1.0' \
    'uvicorn[standard]>=0.29,<1.0' \
    'pdfplumber>=0.11,<1.0'

# Copy service code
COPY . .

# The shared library and config.yaml are mounted at runtime via docker-compose
# PYTHONPATH ensures imports work: `from shared.xxx import yyy`
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
