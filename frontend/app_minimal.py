"""
Streamlit Cloud 연결 테스트용 최소 앱.
배포가 되면 "Hello"가 보입니다. 이 파일로 성공하면 메인 앱(app.py) 쪽 원인입니다.
배포 설정: Main file path = frontend/app_minimal.py, Python 3.11
"""
import streamlit as st

st.set_page_config(page_title="Test", layout="centered")
st.write("Hello — Streamlit Cloud 연결됨.")
