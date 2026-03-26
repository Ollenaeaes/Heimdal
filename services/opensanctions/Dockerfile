FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir psycopg2-binary python-dotenv pydantic pydantic-settings pyyaml

# Download script
COPY scripts/download-opensanctions.sh /app/scripts/
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Batch load script (persist_batch is imported from here)
COPY scripts/load_opensanctions.py /app/scripts/

# Shared library
COPY shared/ /app/shared/

# Sync service
COPY services/opensanctions/sync.py /app/

CMD ["python3", "sync.py"]
