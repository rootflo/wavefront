#!/bin/bash
set -e

export PATH="/app/.venv/bin:$PATH"

echo "Creating Console database if not exists..."
python3 -c "
import psycopg2, os

host = os.environ['CONSOLE_DB_HOST']
user = os.environ['CONSOLE_DB_USERNAME']
password = os.environ['CONSOLE_DB_PASSWORD']
dbname = os.environ['CONSOLE_DB_NAME']

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

cd /app/apps/floconsole/floconsole
exec uv run server.py
