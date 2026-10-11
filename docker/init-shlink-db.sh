#!/bin/sh
set -eu

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --set shlink_db="$SHLINK_DB_NAME" \
    --set shlink_user="$SHLINK_DB_USER" \
    --set shlink_password="$SHLINK_DB_PASSWORD" <<'SQL'
CREATE ROLE :"shlink_user" LOGIN PASSWORD :'shlink_password';
CREATE DATABASE :"shlink_db" OWNER :"shlink_user";
REVOKE CONNECT ON DATABASE :"shlink_db" FROM PUBLIC;
SQL

