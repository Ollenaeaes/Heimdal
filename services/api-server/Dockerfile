# Stage 1: Build frontend (context must be project root)
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
# Build args declared before COPY to bust cache when values change
ARG VITE_CESIUM_ION_TOKEN
ARG VITE_MAPTILER_KEY
ENV VITE_CESIUM_ION_TOKEN=$VITE_CESIUM_ION_TOKEN
ENV VITE_MAPTILER_KEY=$VITE_MAPTILER_KEY
COPY frontend/ .
RUN npx vite build

# Stage 2: Python API server
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    'pydantic>=2.6,<3.0' \
    'pydantic-settings>=2.2,<3.0' \
    'sqlalchemy[asyncio]>=2.0,<3.0' \
    'asyncpg>=0.29,<1.0' \
    'geoalchemy2>=0.14,<1.0' \
    'pyyaml>=6.0,<7.0' \
    'fastapi>=0.110,<1.0' \
    'uvicorn[standard]>=0.29,<1.0' \
    'pdfplumber>=0.11,<1.0' \
    'python-multipart>=0.0.7' \
    'pyarrow>=15.0'

# Copy frontend build output
COPY --from=frontend-build /build/dist /app/static

# Copy service code
COPY services/api-server/ .

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
