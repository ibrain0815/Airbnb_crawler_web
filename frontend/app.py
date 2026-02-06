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


def start_crawl_sync(search_url: str, max_pages: int) -> list[dict] | None:
    """
    동기 크롤링 호출.
    - POST /crawl_sync
    - 서버는 JobManager 에 상태를 저장하지 않고, 결과 JSON 만 반환.
    """
    try:
        r = requests.post(
            f"{_backend_url()}/crawl_sync",
            json={"search_url": search_url, "max_pages": max_pages},
            timeout=600,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "completed":
            st.error(f"크롤링 실패: {data.get('error') or data.get('detail') or '알 수 없는 오류'}")
            return None
        listings = data.get("listings")
        return listings if isinstance(listings, list) else []
    except Exception as e:
        st.error(f"크롤링 호출 실패: {e}")
        return None


def get_excel_from_backend(listings: list[dict]) -> bytes | None:
    """
    프론트에 저장된 listings 를 백엔드로 보내 엑셀 파일 bytes 로 변환.
    - 서버는 요청 범위 내에서만 처리하고, 결과를 저장하지 않음.
    """
    try:
        r = requests.post(
            f"{_backend_url()}/excel-from-listings",
            json={"listings": listings},
            timeout=120,
        )
        r.raise_for_status()
        return r.content
    except Exception as e:
        st.error(f"엑셀 생성 요청 실패: {e}")
        return None


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
    # Step 3: 크롤링 실행 (동기 호출, 결과는 프론트 세션에만 저장)
    # --------------------------------------------------
    st.subheader("3단계: 크롤링 및 엑셀 내보내기")

    if "listings" not in st.session_state:
        st.session_state["listings"] = []

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
                with st.spinner("크롤링 중입니다. 잠시만 기다려 주세요..."):
                    listings = start_crawl_sync(url_to_use, max_pages)
                if listings is not None:
                    st.session_state["listings"] = listings
                    st.session_state["last_crawl_meta"] = {
                        "search_url": url_to_use,
                        "max_pages": max_pages,
                        "total_listings": len(listings),
                        "finished_at": datetime.now().isoformat(timespec="seconds"),
                    }

    listings = st.session_state.get("listings") or []

    if listings:
        meta = st.session_state.get("last_crawl_meta", {})
        st.subheader("📊 크롤링 결과 (로컬 세션에 저장됨)")
        if meta:
            st.caption(
                f"URL: `{meta.get('search_url', '')}` · "
                f"페이지: {meta.get('max_pages', 0)} · "
                f"총 {meta.get('total_listings', len(listings))}건 · "
                f"완료 시각: {meta.get('finished_at', '')}"
            )

        st.dataframe(listings, use_container_width=True)

        st.subheader("엑셀 내보내기")
        excel_bytes = get_excel_from_backend(listings)
        if excel_bytes:
            st.download_button(
                label="엑셀 파일 내보내기",
                data=excel_bytes,
                file_name=f"airbnb_listings_{int(time.time())}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


# Streamlit Cloud는 스크립트를 import 방식으로 실행할 수 있어, __main__일 때만 실행하면 main()이 호출되지 않을 수 있음.
# 따라서 조건 없이 main() 실행 (로컬 streamlit run 시에도 동일하게 실행됨)
try:
    main()
except Exception as e:
    st.error("앱 실행 중 오류가 발생했습니다.")
    st.code(str(e), language=None)
    st.exception(e)
