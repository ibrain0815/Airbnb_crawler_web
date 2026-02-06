"""
Streamlit Cloud / 로컬 공통 진입점 (루트).
Main file path = app.py 로 배포. 여기서 frontend/app.py 를 직접 실행(run_path)하여
그 안의 Streamlit 앱(main 함수)을 구동한다.
"""

import os
import runpy


_root = os.path.dirname(os.path.abspath(__file__))
_frontend_app_path = os.path.join(_root, "frontend", "app.py")

# frontend/app.py 스크립트를 별도 모듈로 실행 (자기 자신을 다시 import 하지 않도록 run_path 사용)
runpy.run_path(_frontend_app_path, run_name="__main__")
