#!/usr/bin/env bash
set -euo pipefail

HOST="${STREAMLIT_SERVER_ADDRESS:-0.0.0.0}"
PORT="${STREAMLIT_SERVER_PORT:-8501}"

exec streamlit run app.py --server.address "$HOST" --server.port "$PORT"
