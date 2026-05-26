from __future__ import annotations
import asyncio
import json
from typing import Any, Callable, Coroutine

from app.core import database as db

Handler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class JobQueue:
    """Persistent async job queue backed by the SQLite jobs table."""

    def __init__(self):
        self._handlers: dict[str, Handler] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._sem = asyncio.Semaphore(3)  # max 3 concurrent jobs

    def register(self, job_type: str, handler: Handler) -> None:
        self._handlers[job_type] = handler

    async def enqueue(
        self,
        job_type: str,
        anime_id: int | None = None,
        episode: int | None = None,
        **payload,
    ) -> int:
        payload_str = json.dumps(payload) if payload else None
        job_id = await db.enqueue_job(job_type, anime_id, episode, payload_str)
        return job_id

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.get_event_loop().create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._process_pending()
                await self._retry_failed()
            except Exception as e:
                print(f"[JobQueue] loop erro: {e}")
            await asyncio.sleep(5)

    async def _process_pending(self) -> None:
        jobs = await db.get_active_jobs()
        tasks = []
        for job_row in jobs:
            job_id, job_type = job_row[0], job_row[1]
            anime_id, episode = job_row[2], job_row[3]
            status = job_row[4]
            payload_str = job_row[7] if len(job_row) > 7 else None

            if status == "running":
                continue

            handler = self._handlers.get(job_type)
            if not handler:
                await db.update_job_status(job_id, "failed", f"No handler for job type: {job_type}")
                continue

            payload = json.loads(payload_str) if payload_str else {}
            payload.update({"anime_id": anime_id, "episode": episode, "job_id": job_id})
            tasks.append(self._run_job(job_id, handler, payload))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_job(self, job_id: int, handler: Handler, payload: dict) -> None:
        async with self._sem:
            await db.update_job_status(job_id, "running")
            try:
                await handler(payload)
                await db.update_job_status(job_id, "done")
            except Exception as e:
                await db.update_job_status(job_id, "failed", str(e))
                print(f"[JobQueue] job {job_id} falhou: {e}")

    async def _retry_failed(self) -> None:
        jobs = await db.get_failed_jobs()
        for job_row in jobs:
            job_id = job_row[0]
            await db.increment_job_retry(job_id)

    async def get_status(self) -> list[dict]:
        jobs = await db.get_active_jobs()
        return [
            {
                "id": j[0],
                "type": j[1],
                "anime_id": j[2],
                "episode": j[3],
                "status": j[4],
                "retries": j[5],
                "error": j[6],
            }
            for j in jobs
        ]


# Global singleton
job_queue = JobQueue()
