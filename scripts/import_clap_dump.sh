#!/usr/bin/env bash
set -euo pipefail

# Import the clap dump files created from the 20260101 railway export.
# Reads DB connection info from the repo's .env (db_host, db_port, db_database, db_username, db_password).

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

DB_HOST="${db_host:-localhost}"
DB_PORT="${db_port:-3306}"
DB_NAME="${db_database:-clap}"
DB_USER="${db_username:-root}"
DB_PASS="${db_password:-}"

if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r raw_key raw_val; do
    [[ -z "$raw_key" || "${raw_key:0:1}" == "#" ]] && continue
    key="$(echo "$raw_key" | tr -d '[:space:]' | tr -d '\r')"
    val="$(echo "$raw_val" | tr -d '\r' | sed 's/^ *//;s/ *$//')"
    case "$key" in
      db_host) DB_HOST="$val" ;;
      db_port) DB_PORT="$val" ;;
      db_database) DB_NAME="$val" ;;
      db_username) DB_USER="$val" ;;
      db_password) DB_PASS="$val" ;;
    esac
  done < "$ENV_FILE"
fi

MYSQL_BASE=(mysql --protocol=TCP -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" --default-character-set=utf8mb4)
mysql_cmd() {
  MYSQL_PWD="$DB_PASS" "${MYSQL_BASE[@]}" "$@"
}

echo "Ensuring database \`$DB_NAME\` exists..."
mysql_cmd -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"

DATA_DIR="$ROOT_DIR/db/data"
FILES=(
  "clap_patient_info.sql"
  "clap_code_mast.sql"
  "clap_assess_score_allocation.sql"
  "clap_assess_score_reference.sql"
  "clap_assess_lst.sql"
  "clap_assess_file_lst.sql"
  "clap_assess_score.sql"
  "clap_assess_score_t.sql"
  "clap_patient_api_key.sql"
)

for file in "${FILES[@]}"; do
  path="$DATA_DIR/$file"
  echo "Importing $file..."
  mysql_cmd "$DB_NAME" < "$path"
done

echo "Import complete."
