"""
Streamlit Cloud 진입점 (루트).
Main file path = app.py 로 배포. import 시 frontend/app.py 가 로드되며 그 안에서 main() 실행됨.
"""
import sys
import os

_root = os.path.dirname(os.path.abspath(__file__))
_frontend = os.path.join(_root, "frontend")
if _frontend not in sys.path:
    sys.path.insert(0, _frontend)

# frontend/app.py 로드 → 해당 파일 끝에서 main() 호출됨
import app as _frontend_app
