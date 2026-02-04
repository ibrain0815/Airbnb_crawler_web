# 에어비앤비 숙소 정보 크롤러 (웹)

에어비앤비 검색 결과에서 **숙소명, 금액, 주소, 평점**을 수집해 엑셀로 저장하는 웹 앱입니다.

- **백엔드**: FastAPI + Selenium (headless Chrome)
- **프론트엔드**: Streamlit (진행률·결과 표시, 엑셀 다운로드)

---

## 목차

- [주요 기능](#주요-기능)
- [프론트엔드 기능](#프론트엔드-기능)
- [백엔드 기능](#백엔드-기능)
- [로컬 실행 방법](#로컬-실행-방법)
- [Streamlit 배포](#streamlit-배포)
- [API](#api)
- [수동 API 테스트](#수동-api-테스트)
- [봇 감지 우회](#봇-감지-우회)
- [환경 변수](#환경-변수)
- [주의사항](#주의사항)
- [프로젝트 구조](#프로젝트-구조)

---

## 주요 기능

| 구분 | 내용 |
|------|------|
| **크롤링** | 에어비앤비 검색 URL 입력 후 최대 1~20페이지 자동 수집 |
| **수집 항목** | 숙소명, 가격, 상세설명(주소), 평점/후기, 링크 |
| **수집 방식** | JavaScript `execute_script` 고속 수집 + 다중 fallback CSS 선택자 |
| **실시간 진행** | 1초 간격 상태 폴링, 진행률 바·수집 건수·진행 로그·데이터프레임 표시 |
| **엑셀 내보내기** | 번호, 숙소명, 가격, 상세설명, 평점/후기, 링크 컬럼, 헤더 서식·열 너비 자동 조절 |
| **에러 처리** | 작업 없음(404) 시 안내 메시지 후 입력 폼 복귀, 백엔드 미연결 시 안내 |
| **봇 감지 우회** | CDP로 `navigator.webdriver` 숨김, 랜덤 지연, (선택) undetected-chromedriver |

---

## 프론트엔드 기능

- **1단계**: 에어비앤비 접속 버튼 → 새 탭에서 에어비앤비 열기
- **2단계**: 검색 결과 URL 수동 복사·붙여넣기, 최대 크롤링 페이지 수(1~20) 선택
- **3단계**: 크롤링 시작 → 백엔드 연결 확인 후 `POST /crawl` 호출, `job_id` 저장
- **진행 현황**: 1초 간격 `GET /crawl/{job_id}/status/json` 폴링
  - 진행률 바(`st.progress`), 상태·현재 페이지·수집 건수·진행률 표
  - 진행 로그(최근 20줄, 타임스탬프 포함)
  - 수집 결과 실시간 데이터프레임
- **완료 후**: 엑셀 파일 내보내기 버튼 → `GET /crawl/{job_id}/download`로 `.xlsx` 다운로드
- **404 처리**: `job_id` 없음 시 "작업을 찾을 수 없습니다…" 메시지, `session_state` 초기화 후 `st.rerun()`으로 입력 폼 복귀
- **설정**: `BACKEND_URL`(기본 `http://localhost:8000`). 로컬에서 8503 포트로 쓰려면 `frontend/run_local.bat`(Windows) 또는 `run_local.sh`(Mac/Linux) 실행, 또는 `streamlit run app.py --server.port 8503`

---

## 백엔드 기능

- **작업 관리**: `JobManager` — UUID `job_id`, `pending` → `running` → `completed`/`failed`, 스레드 안전(Lock), 페이지별 콜백으로 수집 결과 누적
- **크롤러**: headless Chrome, `create_driver`(일반 Selenium 또는 `USE_UNDETECTED_CHROME=1` 시 undetected-chromedriver), CDP stealth, `get_airbnb_listings`(JS 일괄 수집 + 카드별 fallback), `go_to_next_page`(다음 버튼/스크롤), `run_crawl`(페이지 루프·드라이버 종료 보장)
- **API**: `POST /crawl`(백그라운드 스레드로 크롤링 시작), `GET /crawl/{job_id}/status/json`(폴링용), `GET /crawl/{job_id}/status`(SSE 1초 스트리밍), `GET /crawl/{job_id}/download`(엑셀), `GET /health`
- **엑셀**: `save_listings_to_excel` — 파일 시스템 없이 bytes 반환, 헤더(파란 배경·흰 글씨), 셀 테두리·줄바꿈·열 너비 자동

## 로컬 실행 방법

### 1. 백엔드 실행

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

- 기본 주소: `http://localhost:8000`
- API 문서: `http://localhost:8000/docs`

### 2. 프론트엔드 실행

```bash
pip install -r requirements.txt
cd frontend
streamlit run app.py
```

- **8503 포트로 실행**: `frontend` 폴더에서 `run_local.bat`(Windows) 또는 `./run_local.sh`(Mac/Linux) 실행 → **http://localhost:8503**  
  또는 `streamlit run app.py` 만 실행 시 기본 **http://localhost:8501**

### 3. 사용 순서

1. 브라우저에서 **http://localhost:8503** 접속 (위에서 8503으로 실행한 경우. 기본 실행이면 **http://localhost:8501**)
2. **에어비앤비 접속** 버튼 클릭 → 에어비앤비(https://www.airbnb.co.kr/)가 새 탭에서 열림
3. 에어비앤비에서 **숙박지 페이지**(검색·필터 적용한 결과)를 선택한 뒤, **주소창의 URL**을 복사
4. 앱 화면으로 돌아와 **검색 결과 URL** 입력란에 붙여넣기, 최대 크롤링 페이지 수 선택 (1~20)
5. **크롤링 시작** 클릭 → 진행률·수집 건수 확인
6. 완료 후 **엑셀 파일 내보내기**로 결과 저장

---

## Streamlit 배포

**Streamlit Community Cloud**에 프론트엔드만 배포할 수 있습니다. 백엔드(FastAPI + Selenium)는 Streamlit Cloud에서 실행할 수 없으므로 **별도 서버**(Railway, Render, Fly.io, VM 등)에 배포한 뒤, 아래 Secrets에 해당 URL을 넣어 연결합니다.

### 1. 저장소 연결

1. [share.streamlit.io](https://share.streamlit.io) 로그인 후 **New app** 선택
2. **Repository**: 본인 GitHub `사용자명/저장소명` 선택
3. **Branch**: `main` (또는 사용 중인 브랜치)
4. **Main file path**: **`app.py`** (저장소 **루트**의 app.py. 이 파일이 frontend 앱을 불러옵니다.)
5. **Advanced settings**에서 **Python version**을 **3.11**로 선택 (필수).
   - 3.13 사용 시 서버가 기동하지 않아 "connection refused" / "Error running app" 이 발생할 수 있습니다. 앱을 이미 만든 경우, 앱을 삭제한 뒤 새로 만들 때 Python 3.11을 선택하세요.

### 2. Secrets 설정

앱 설정 화면에서 **Secrets** 탭에 아래처럼 TOML 형식으로 입력합니다.

```toml
BACKEND_URL = "https://your-backend-api.com"
```

- `https://your-backend-api.com` 자리에는 실제로 배포한 백엔드 주소를 넣습니다 (끝에 `/` 제외).
- 로컬에서는 `frontend/.env`의 `BACKEND_URL`을 사용하고, Cloud에서는 이 Secrets가 우선합니다.

### 3. 배포 실행

**Deploy!** 클릭 후 빌드·실행이 끝나면 앱 URL이 생성됩니다. 해당 URL에서 프론트엔드만 사용하며, 크롤링 요청은 Secrets에 넣은 백엔드로 전달됩니다.

### 4. "Error running app" / "connection refused" 발생 시

- **포트**: Cloud는 **8501**로 health check 합니다. `config.toml`에 `port = 8503`을 두면 앱은 8503에서만 대기해 **connection refused**가 납니다. 현재는 port를 지정하지 않아 기본 8501을 쓰도록 했습니다.
- **Python 3.11**: **3.13**이면 기동 실패가 나는 경우가 있으므로, 앱 삭제 후 새 앱 생성 시 **Advanced settings에서 Python version을 3.11**로 선택해 배포하세요.
- **로컬**: `cd frontend` 후 `streamlit run app.py` 실행. 8503 포트로 쓰려면 `streamlit run app.py --server.port 8503`
- **루트 진입점**: Cloud에서 **Main file path = app.py**(루트) 사용 시, 루트 app.py가 frontend 앱을 불러와 기동합니다.
- **Cloud 로그**: 앱 설정 → **Logs** 탭에서 빌드/런타임 오류 확인.

### 5. 요약

| 항목 | 내용 |
|------|------|
| 배포 대상 | **프론트엔드(Streamlit)만** Streamlit Cloud에 배포 |
| 백엔드 | 별도 호스팅 필요 (Selenium/Chrome 사용) |
| 메인 파일 | 루트 `app.py` (frontend 앱 로드) |
| 의존성 | 루트 `requirements.txt` 사용 (streamlit, requests, python-dotenv) |
| Secrets | `BACKEND_URL` = 배포된 백엔드 API URL |

---

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/crawl` | 크롤링 작업 시작. body: `{ "search_url": "URL", "max_pages": 1~20 }` → `{ "job_id": "uuid" }` |
| GET | `/crawl/{job_id}/status/json` | 작업 상태 JSON 한 번 반환 (폴링용) |
| GET | `/crawl/{job_id}/status` | SSE로 1초 간격 상태 스트리밍 |
| GET | `/crawl/{job_id}/download` | 수집 결과 엑셀 파일 다운로드 (미완료 시 400) |
| GET | `/health` | 헬스체크 |

- **작업 상태**: `pending` → `running` → `completed` 또는 `failed`
- **status/json 응답 필드**: `status`, `current_page`, `max_pages`, `total_listings`, `listings`, `progress_percent`, `error_message`(실패 시)
- **다운로드 파일명**: `airbnb_listings_{timestamp}.xlsx` (서버에서 생성한 이름으로 전달)

## 수동 API 테스트

```bash
# 헬스체크
curl http://localhost:8000/health

# 크롤링 작업 시작
curl -X POST http://localhost:8000/crawl -H "Content-Type: application/json" -d "{\"search_url\": \"https://www.airbnb.co.kr/homes\", \"max_pages\": 2}"
# 응답: {"job_id":"uuid-string"}
```

## 봇 감지 우회

크롤링 시 사이트 봇 감지를 완화하기 위해 다음을 적용했습니다.

| 방법 | 설명 |
|------|------|
| **CDP 스크립트** | 모든 페이지 로드 시 `navigator.webdriver`를 숨김 (Chrome 79+) |
| **Chrome 옵션** | `--disable-blink-features=AutomationControlled`, `excludeSwitches: enable-automation` |
| **랜덤 지연** | 첫 로드 2~4초, 페이지 전환·스크롤 후 1~2.5초 등 인간형 지연 |
| **undetected-chromedriver** (선택) | `USE_UNDETECTED_CHROME=1` 로 두면 감지 우회용 드라이버 사용 (강한 감지 시 권장) |

감지가 심할 때: 백엔드 `.env`에 `USE_UNDETECTED_CHROME=1` 설정 후 재시작.  
그래도 차단되면 프록시·VPN·요청 간격 늘리기 등을 검토하세요.

## 환경 변수

| 위치 | 변수 | 설명 |
|------|------|------|
| frontend | `BACKEND_URL` | 백엔드 API 주소 (기본: `http://localhost:8000`) |
| backend | (선택) `PORT`, `LOG_LEVEL` | .env.example 참고 |
| backend | `USE_UNDETECTED_CHROME` | `1` 이면 undetected-chromedriver 사용 (봇 감지 우회 강화) |

- **Streamlit Cloud** 배포 시: 앱 설정 → Secrets에 `BACKEND_URL = "https://배포한-백엔드-주소"` (TOML) 입력. 앱은 Secrets를 우선 사용합니다.

## 주의사항

- **Streamlit Cloud**에서는 Selenium 실행이 불가하므로, 백엔드는 별도 서버(VM/컨테이너 등)에 배포해야 합니다.
- 에어비앤비는 봇 감지·IP 제한이 있을 수 있어, 클라우드 IP에서 차단될 수 있습니다. 이 경우 트래픽 제한 완화·재시도·프록시 등 환경에 맞게 조정이 필요할 수 있습니다.
- 백엔드를 재시작하면 기존 `job_id`는 사라지며, 해당 작업으로 상태/다운로드 요청 시 404가 발생합니다. 프론트엔드에서는 이 경우 안내 후 크롤링을 다시 시작하도록 유도합니다.

## 프로젝트 구조

```
backend/
  main.py         # FastAPI: POST /crawl, GET status/json, GET status(SSE), GET download, /health
  crawler.py      # Selenium: create_driver, _apply_stealth_cdp, get_airbnb_listings(JS+fallback), go_to_next_page, run_crawl
  job_manager.py  # 작업 상태 관리 (UUID, Lock, status: pending/running/completed/failed)
  excel_utils.py  # 엑셀 bytes 생성 (번호, 숙소명, 가격, 상세설명, 평점/후기, 링크), 서식·열 너비
  requirements.txt   # fastapi, uvicorn, selenium, webdriver-manager, openpyxl, undetected-chromedriver 등
  .env.example
frontend/
  app.py          # Streamlit: 3단계 UI, _get_backend_url(Secrets/.env), 진행률·엑셀 다운로드
  run_local.bat   # Windows: 8503 포트로 로컬 실행
  run_local.sh    # Mac/Linux: 8503 포트로 로컬 실행
  .streamlit/config.toml  # headless, gatherUsageStats (port 미지정 → Cloud 8501 통과)
  .env.example
app.py                  # 루트: Streamlit Cloud 진입점 (frontend 앱 로드)
.streamlit/config.toml  # 루트: Cloud 필수 (config는 루트에 두어야 함)
requirements.txt        # 루트: Cloud 배포 시 의존성
README.md
```
