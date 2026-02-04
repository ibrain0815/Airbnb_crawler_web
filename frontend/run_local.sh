#!/bin/sh
cd "$(dirname "$0")"
streamlit run app.py --server.port 8503
