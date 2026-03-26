FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir psycopg2-binary lxml requests python-dotenv

COPY services/paris-mou/update.py /app/
COPY shared/ /app/shared/

CMD ["python3", "update.py"]
