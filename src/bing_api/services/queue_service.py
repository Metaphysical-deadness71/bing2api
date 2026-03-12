import asyncio
from datetime import datetime
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional

from bing_api.models.video import RetryJobRequest, VideoGenerationRequest, VideoGenerationResponse
from bing_api.services.video_service import VideoService


@dataclass
class QueueItem:
    job_id: str
    request: VideoGenerationRequest
    retried_from_job_id: Optional[str] = None


class JobQueueService:
    def __init__(self, video_service: VideoService, concurrency: int = 2) -> None:
        self.video_service = video_service
        self.concurrency = max(1, concurrency)
        self.queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._workers = []
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for index in range(self.concurrency):
            self._workers.append(asyncio.create_task(self._worker(index), name="bing-job-worker-{0}".format(index)))

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            with suppress(asyncio.CancelledError):
                await worker
        self._workers.clear()

    async def update_concurrency(self, concurrency: int) -> None:
        next_concurrency = max(1, int(concurrency))
        if next_concurrency == self.concurrency:
            return
        await self.stop()
        self.concurrency = next_concurrency
        await self.start()

    async def enqueue_generation(self, request: VideoGenerationRequest) -> VideoGenerationResponse:
        queued = await self.video_service.create_queued_generation(request)
        await self.queue.put(QueueItem(job_id=queued.job_id, request=request))
        return queued

    async def enqueue_retry(self, job_id: str, request: RetryJobRequest) -> VideoGenerationResponse:
        queued = await self.video_service.create_retry_placeholder(job_id, request)
        snapshot = await self.video_service.build_retry_request(job_id, request)
        await self.queue.put(QueueItem(job_id=queued.job_id, request=snapshot, retried_from_job_id=job_id))
        return queued

    async def _worker(self, worker_index: int) -> None:
        while True:
            item = await self.queue.get()
            try:
                await self.video_service.process_queued_generation(
                    item.request,
                    queued_job_id=item.job_id,
                    retried_from_job_id=item.retried_from_job_id,
                )
            except Exception as exc:
                response = await self.video_service.job_store.get(item.job_id)
                if response is not None:
                    response.status = "failed"
                    response.queue_status = "failed"
                    response.message = "队列执行失败: {0}".format(str(exc))
                    response.updated_at = datetime.utcnow()
                    await self.video_service.job_store.put(response)
            finally:
                self.queue.task_done()
