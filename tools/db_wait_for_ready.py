#!/usr/bin/env python3

import os
import socket
import sys
import time


def get_db_config() -> dict:
    return {
        "host": os.environ.get("POSTGRES_HOST", "").strip() or "localhost",
        "port": 5432,
        "user": os.environ.get("POSTGRES_USER", "").strip() or "root",
        "password": os.environ.get("POSTGRES_PASS", "").strip() or "root",
        "dbname": os.environ.get("POSTGRES_DB", "").strip() or "agent",
    }


def check_db_ready(db_config: dict) -> bool:
    host = db_config["host"]
    port = db_config["port"]
    try:
        sock = socket.create_connection((host, port), timeout = 5)
        sock.close()
    except (OSError, socket.timeout):
        return False

    try:
        import psycopg2
        conn = psycopg2.connect(
            host = host,
            port = port,
            user = db_config["user"],
            password = db_config["password"],
            dbname = db_config["dbname"],
            connect_timeout = 5,
        )
        conn.close()
        return True
    except Exception:
        return False


def main():
    max_retries = 7
    retry_interval = 5
    db_config = get_db_config()

    print(f"Waiting for database at {db_config['host']}:{db_config['port']}...")

    for attempt in range(1, max_retries + 1):
        if check_db_ready(db_config):
            print("Database is ready.")
            return 0
        print(f"Database not ready (attempt {attempt}/{max_retries}). Retrying in {retry_interval}s...")
        time.sleep(retry_interval)

    print(f"Database did not become ready after {max_retries} attempts.", file = sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
