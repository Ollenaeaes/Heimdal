FROM timescale/timescaledb-ha:pg16
USER root
RUN apt-get update && apt-get install -y postgresql-16-postgis-3 && rm -rf /var/lib/apt/lists/*
USER postgres
COPY migrations/ /docker-entrypoint-initdb.d/migrations/
COPY init.sh /docker-entrypoint-initdb.d/
