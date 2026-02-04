"""
크롤링 작업 상태 관리
작업 ID(UUID), 상태(pending/running/completed/failed), 수집 결과·현재 페이지·진행율 저장.
스레드 안전: threading.Lock 사용.
"""

import logging
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


class JobManager:
    """작업별 상태 및 결과 저장, 스레드 안전 접근."""

    _lock = threading.Lock()
    _jobs: dict[str, dict[str, Any]] = {}

    @classmethod
    def create_job(cls, search_url: str, max_pages: int) -> str:
        """작업 생성 후 job_id(UUID) 반환."""
        job_id = str(uuid.uuid4())
        with cls._lock:
            cls._jobs[job_id] = {
                "job_id": job_id,
                "status": STATUS_PENDING,
                "search_url": search_url,
                "max_pages": max_pages,
                "current_page": 0,
                "listings": [],
                "progress_percent": 0.0,
                "error_message": None,
            }
        logger.info("작업 생성: job_id=%s, max_pages=%s", job_id, max_pages)
        return job_id

    @classmethod
    def get_status(cls, job_id: str) -> dict[str, Any] | None:
        """작업 상태 조회 (스레드 안전)."""
        with cls._lock:
            return cls._jobs.get(job_id)

    @classmethod
    def set_running(cls, job_id: str) -> None:
        """상태를 running 으로 변경."""
        with cls._lock:
            if job_id in cls._jobs:
                cls._jobs[job_id]["status"] = STATUS_RUNNING

    @classmethod
    def set_page_result(
        cls,
        job_id: str,
        current_page: int,
        new_listings: list[dict],
        all_listings: list[dict],
    ) -> None:
        """현재 페이지 및 수집 결과·진행율 업데이트."""
        with cls._lock:
            if job_id not in cls._jobs:
                return
            job = cls._jobs[job_id]
            job["current_page"] = current_page
            job["listings"] = list(all_listings)
            max_pages = job.get("max_pages", 1)
            job["progress_percent"] = round(100.0 * current_page / max_pages, 1) if max_pages else 0.0

    @classmethod
    def set_completed(cls, job_id: str) -> None:
        """상태를 completed 로 변경."""
        with cls._lock:
            if job_id in cls._jobs:
                cls._jobs[job_id]["status"] = STATUS_COMPLETED
                job = cls._jobs[job_id]
                job["progress_percent"] = 100.0
                job["current_page"] = job.get("max_pages", 0)

    @classmethod
    def set_failed(cls, job_id: str, error_message: str) -> None:
        """상태를 failed 로 변경하고 에러 메시지 저장."""
        with cls._lock:
            if job_id in cls._jobs:
                cls._jobs[job_id]["status"] = STATUS_FAILED
                cls._jobs[job_id]["error_message"] = error_message
        logger.warning("작업 실패: job_id=%s, error=%s", job_id, error_message)

    @classmethod
    def get_listings(cls, job_id: str) -> list[dict]:
        """수집된 목록 반환 (스레드 안전)."""
        with cls._lock:
            job = cls._jobs.get(job_id)
            return list(job["listings"]) if job else []
