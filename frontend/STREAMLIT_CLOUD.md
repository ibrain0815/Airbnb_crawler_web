# Streamlit Community Cloud 배포 시

- **Python 버전**: **Advanced settings**에서 **Python 3.11** 선택 (3.13이면 connection refused 발생 가능).
- **Main file path**: **`app.py`** (저장소 **루트**의 app.py 사용. 이 파일이 frontend 앱을 불러옴.)
- **Secrets**: `BACKEND_URL = "https://배포한-백엔드-URL"` (끝에 `/` 제외)
- **설정**: `.streamlit/config.toml`은 **루트**에 있어야 합니다 (이미 있음).

**connection refused가 나면:** 앱 삭제 후 **Python 3.11**로 새 앱 생성하고, Main file path를 **app.py**(루트)로 두고 다시 배포하세요.
