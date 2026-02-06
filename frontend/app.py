"""
Streamlit 프론트엔드 — 에어비앤비 크롤링 UI.

- 에어비앤비 접속 → 숙박 페이지 선택 후, 주소창 URL을 복사해 아래 입력란에 붙여넣기
- 크롤링 시작 시 해당 URL로 수집, 진행 현황 실시간 표시 → 엑셀 내보내기
"""
import os
import time
from datetime import datetime
from typing import Any

import requests
import streamlit as st


def _get_backend_url() -> str:
    """로컬은 .env, Streamlit Cloud는 Secrets에서 BACKEND_URL 읽기."""
    try:
        if hasattr(st, "secrets") and st.secrets is not None:
            url = st.secrets.get("BACKEND_URL")
            if url:
                return str(url).rstrip("/")
    except Exception:
        pass
    return os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


# 지연 계산: import 시 st.secrets 미준비로 오류 나는 것 방지 (Streamlit Cloud 등)
def _backend_url() -> str:
    """매번 조회 (session_state 미사용으로 Cloud 초기화 이슈 회피)."""
    return _get_backend_url()


AIRBNB_URL = "https://www.airbnb.co.kr/"


def check_backend() -> bool:
    """백엔드 연결 확인."""
    try:
        r = requests.get(f"{_backend_url()}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def start_crawl(search_url: str, max_pages: int) -> str | None:
    """POST /crawl 호출 후 job_id 반환. 실패 시 None."""
    try:
        r = requests.post(
            f"{_backend_url()}/crawl",
            json={"search_url": search_url, "max_pages": max_pages},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("job_id")
    except Exception as e:
        st.error(f"크롤링 시작 실패: {e}")
        return None


def fetch_status(job_id: str) -> dict:
    """현재 상태 1회 조회. 실패 시 failed 상태 반환."""
    try:
        r = requests.get(f"{_backend_url()}/crawl/{job_id}/status/json", timeout=10)
        if r.status_code == 404:
            return {
                "status": "failed",
                "error_message": "작업을 찾을 수 없습니다. (백엔드 재시작 시 이전 작업은 사라집니다) 크롤링을 다시 시작해 주세요.",
                "job_not_found": True,
            }
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": "failed", "error_message": str(e)}
    except Exception as e:
        return {"status": "failed", "error_message": str(e)}


def get_download_url(job_id: str) -> str:
    return f"{_backend_url()}/crawl/{job_id}/download"


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    st.set_page_config(page_title="에어비앤비 숙소 크롤러", layout="centered")
    st.title("에어비앤비 숙소 정보 크롤러")

    # --------------------------------------------------
    # Step 1: 에어비앤비 접속
    # --------------------------------------------------
    st.subheader("1단계: 에어비앤비 접속")
    st.markdown(
        '<a href="' + AIRBNB_URL + '" target="_blank" rel="noopener noreferrer" '
        'style="display:inline-block; background:#FF5A5F; color:white; padding:0.6rem 1.2rem; '
        'text-decoration:none; border-radius:8px; font-weight:bold;">🔗 에어비앤비 접속</a>',
        unsafe_allow_html=True,
    )
    st.caption("버튼을 누르면 에어비앤비가 새 탭에서 열립니다.")

    st.divider()

    # --------------------------------------------------
    # Step 2: 숙박지 페이지 URL — 수동 복사·붙여넣기
    # --------------------------------------------------
    st.subheader("2단계: 숙박지 페이지 URL")
    st.info(
        "에어비앤비에서 **숙박 검색 결과 페이지**로 이동한 뒤, **주소창의 URL**을 복사(Ctrl+C)하여 아래 입력란에 **붙여넣기(Ctrl+V)** 해 주세요."
    )

    search_url = st.text_input(
        "검색 결과 URL (숙박지 페이지 주소)",
        value="",
        placeholder="https://www.airbnb.co.kr/s/서울/homes?...",
        help="에어비앤비 숙박 검색 결과 페이지의 주소를 복사해 붙여넣으세요.",
        key="search_url",
    )
    max_pages = st.number_input(
        "최대 크롤링 페이지 수",
        min_value=1,
        max_value=20,
        value=5,
        step=1,
        help="수집할 최대 페이지 수 (1페이지당 여러 개 숙소)",
    )

    st.divider()

    # --------------------------------------------------
    # Step 3: 크롤링 실행 (백그라운드 + 진행률 폴링)
    # --------------------------------------------------
    st.subheader("3단계: 크롤링 및 엑셀 내보내기")
    if st.button("크롤링 시작", type="primary"):
        url_to_use = (search_url or "").strip()
        if not url_to_use:
            st.warning("2단계에서 검색 결과 URL을 복사해 붙여넣어 주세요.")
        else:
            if not check_backend():
                st.error(
                    f"백엔드에 연결할 수 없습니다. ({_backend_url()})\n\n"
                    "백엔드를 먼저 실행해 주세요:\n"
                    "`cd backend` 후 `python -m uvicorn main:app --reload`"
                )
            else:
                job_id = start_crawl(url_to_use, max_pages)
                if job_id:
                    st.session_state["job_id"] = job_id
                    st.session_state["max_pages"] = max_pages
                    st.session_state["progress_log"] = []

    job_id = st.session_state.get("job_id")
    if not job_id:
        return

    # --------------------------------------------------
    # 진행 현황 (실시간)
    # --------------------------------------------------
    if "progress_log" not in st.session_state:
        st.session_state["progress_log"] = []

    st.subheader("📊 크롤링 진행 현황")
    st.caption("백엔드에서 상태를 가져오는 중… 연결이 안 되면 아래에 오류가 표시됩니다.")
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    log_placeholder = st.empty()
    table_placeholder = st.empty()

    last_data: dict[str, Any] = {}
    data = fetch_status(job_id)
    last_data = data
    with st.expander("백엔드 상태 응답 (JSON)", expanded=False):
        st.json(data)
    status = data.get("status", "")
    current = data.get("current_page", 0)
    total = data.get("max_pages", 1) or 1
    total_listings = data.get("total_listings", 0)
    listings = data.get("listings") if isinstance(data.get("listings"), list) else []
    progress_pct = data.get("progress_percent", 0) or (100 * current / total if total else 0)

    # 로그 한 줄 추가
    ts = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{ts}] 페이지 {current}/{total} · 수집 {total_listings}건 · 상태: {status}"
    if not st.session_state["progress_log"] or st.session_state["progress_log"][-1] != log_line:
        st.session_state["progress_log"].append(log_line)

    # 진행률 바
    progress_placeholder.progress(progress_pct / 100.0)

    # 요약 상태
    status_placeholder.markdown(
        f"""
        | 항목 | 값 |
        |------|-----|
        | **상태** | `{status}` |
        | **현재 페이지** | {current} / {total} |
        | **수집 건수** | **{total_listings}건** |
        | **진행률** | {progress_pct:.1f}% |
        """
    )

    # 진행 로그 (최근 20줄)
    log_text = "\n".join(st.session_state["progress_log"][-20:])
    log_placeholder.code(log_text or "대기 중...", language=None)

    if listings:
        table_placeholder.dataframe(listings, use_container_width=True)

    if status == "failed":
        err_msg = data.get("error_message") or "알 수 없는 오류"
        st.error(err_msg)
        if "job_id" in st.session_state:
            del st.session_state["job_id"]
        st.info("아래에서 URL을 입력한 뒤 **크롤링 시작**을 다시 눌러 주세요.")
        if st.button("처음으로 (입력 화면으로 돌아가기)", type="primary"):
            st.rerun()
        st.stop()
    if status == "completed":
        st.success(f"크롤링 완료: 총 {total_listings}건 수집")
    else:
        auto = st.checkbox("자동 갱신(2초)", value=True)
        if st.button("상태 새로고침"):
            st.rerun()
        if auto:
            time.sleep(2)
            st.rerun()

    # 엑셀 내보내기
    listings_for_download = last_data.get("listings") if isinstance(last_data.get("listings"), list) else []
    if last_data.get("status") == "completed" and listings_for_download:
        st.subheader("엑셀 내보내기")
        try:
            resp = requests.get(get_download_url(job_id), timeout=30)
            if resp.status_code == 200:
                st.download_button(
                    label="엑셀 파일 내보내기",
                    data=resp.content,
                    file_name=f"airbnb_listings_{int(time.time())}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.warning("엑셀 다운로드 준비 중 오류가 발생했습니다.")
        except Exception as e:
            st.error(f"다운로드 요청 실패: {e}")


# Streamlit Cloud는 스크립트를 import 방식으로 실행할 수 있어, __main__일 때만 실행하면 main()이 호출되지 않을 수 있음.
# 따라서 조건 없이 main() 실행 (로컬 streamlit run 시에도 동일하게 실행됨)
try:
    main()
except Exception as e:
    st.error("앱 실행 중 오류가 발생했습니다.")
    st.code(str(e), language=None)
    st.exception(e)
