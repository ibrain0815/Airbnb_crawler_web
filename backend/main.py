"""
FastAPI 백엔드 — 크롤링 작업 시작, SSE 상태 스트리밍, 엑셀 다운로드, 헬스체크.
"""

import json
import logging
import threading
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from crawler import run_crawl
from job_manager import JobManager
from excel_utils import save_listings_to_excel, get_excel_filename

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="에어비앤비 크롤러 API", version="1.0.0")

# Streamlit Cloud 등 다른 도메인에서 API 호출 시 필요
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CrawlRequest(BaseModel):
    search_url: str = Field(..., description="에어비앤비 검색 URL")
    max_pages: int = Field(5, ge=1, le=20, description="최대 크롤링 페이지 수")


def _run_crawl_background(job_id: str, search_url: str, max_pages: int) -> None:
    """백그라운드 스레드에서 크롤링 실행, JobManager 로 상태 갱신."""
    try:
        JobManager.set_running(job_id)

        def on_page(page: int, page_listings: list[dict], all_listings: list[dict]) -> None:
            JobManager.set_page_result(job_id, page, page_listings, all_listings)

        run_crawl(search_url, max_pages, on_page_result=on_page)
        JobManager.set_completed(job_id)
    except Exception as e:
        logger.exception("크롤링 실패: %s", e)
        JobManager.set_failed(job_id, str(e))


@app.post("/crawl")
def start_crawl(req: CrawlRequest) -> dict[str, str]:
    """
    크롤링 작업 시작.
    body: { "search_url": "https://www.airbnb.co.kr/s/서울?...", "max_pages": 5 }
    response: { "job_id": "uuid-string" }
    """
    job_id = JobManager.create_job(req.search_url, req.max_pages)
    thread = threading.Thread(
        target=_run_crawl_background,
        args=(job_id, req.search_url, req.max_pages),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/crawl/{job_id}/status/json")
def get_crawl_status_json(job_id: str) -> dict:
    """현재 작업 상태를 JSON 한 번 반환 (폴링용)."""
    job = JobManager.get_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    listings = job.get("listings")
    if not isinstance(listings, list):
        listings = []
    return {
        "status": job["status"],
        "current_page": job["current_page"],
        "max_pages": job.get("max_pages", 0),
        "total_listings": len(listings),
        "listings": listings,
        "progress_percent": job.get("progress_percent", 0),
        "error_message": job.get("error_message"),
    }


@app.get("/crawl/{job_id}/status")
def stream_crawl_status(job_id: str):
    """
    SSE: 1초 간격으로 현재 상태 스트리밍.
    event data: { "status", "current_page", "total_listings", "listings", "progress_percent", "error_message" }
    완료/실패 시 마지막 이벤트 후 스트림 종료.
    """
    def generate() -> Any:
        while True:
            job = JobManager.get_status(job_id)
            if job is None:
                yield f"data: {json.dumps({'error': 'job not found'})}\n\n"
                return
            payload = {
                "status": job["status"],
                "current_page": job["current_page"],
                "max_pages": job.get("max_pages", 0),
                "total_listings": len(job.get("listings", [])),
                "listings": job.get("listings", []),
                "progress_percent": job.get("progress_percent", 0),
            }
            if job.get("error_message"):
                payload["error_message"] = job["error_message"]
            yield f"data: {json.dumps(payload)}\n\n"
            if job["status"] in ("completed", "failed"):
                return
            time.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/crawl/{job_id}/download")
def download_crawl_result(job_id: str):
    """수집 결과를 엑셀로 생성해 FileResponse 로 반환."""
    job = JobManager.get_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"job not completed (status={job['status']})",
        )
    listings = JobManager.get_listings(job_id)
    content = save_listings_to_excel(listings)
    filename = get_excel_filename()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
def health() -> dict[str, str]:
    """헬스체크."""
    return {"status": "ok"}
