#!/bin/bash
set -e

export PATH="/app/.venv/bin:$PATH"

if [ "${FLOWARE_DB_CREATE}" = "true" ]; then
    echo "Creating Floware database if not exists..."
    python3 -c "
import psycopg2, os

host = os.environ['DB_HOST']
user = os.environ['DB_USERNAME']
password = os.environ['DB_PASSWORD']
dbname = os.environ['DB_NAME']

conn = psycopg2.connect(host=host, user=user, password=password, dbname='postgres')
conn.autocommit = True
cur = conn.cursor()
cur.execute(\"SELECT 1 FROM pg_database WHERE datname = %s\", (dbname,))

if not cur.fetchone():
    cur.execute('CREATE DATABASE \"' + dbname.replace('\"', '\"\"') + '\"')
    print('Database created')
else:
    print('Database already exists, skipping')
conn.close()
"
else
    echo "FLOWARE_DB_CREATE is not true, skipping database creation"
fi

cd /app/apps/floware/floware
exec uv run server.py
