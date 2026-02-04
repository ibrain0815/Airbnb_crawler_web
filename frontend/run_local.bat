@echo off
cd /d "%~dp0"
streamlit run app.py --server.port 8503
