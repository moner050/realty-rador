"""네트워크 producer와 단일 DB connection writer 사이의 bounded queue."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import monotonic
from typing import Callable

from sqlalchemy.orm import Session

from realty_radar.application.listing_batch_writer import BatchCommitResult, IncomingListing, ListingBatchWriter


@dataclass(frozen=True, slots=True)
class _Flush:
    done: Event


@dataclass(frozen=True, slots=True)
class _Stop:
    done: Event


class BoundedBatchWriter:
    """하나의 thread/session이 500건 또는 1초마다 저장한다.

    writer thread가 세션과 MySQL connection을 소유하므로 temporary staging table은
    worker 수명 동안 유지된다. producer는 queue가 찼을 때만 양보한다.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        job_id: int,
        *,
        max_queue_size: int = 2_000,
        batch_size: int = 500,
        flush_seconds: float = 1.0,
    ):
        self._session_factory = session_factory
        self._job_id = job_id
        self._batch_size = batch_size
        self._flush_seconds = flush_seconds
        self._queue: Queue[IncomingListing | _Flush | _Stop] = Queue(maxsize=max_queue_size)
        self._thread = Thread(target=self._run, name=f"listing-writer-{job_id}", daemon=True)
        self._started = False
        self._closed = False
        self._failure: BaseException | None = None
        self._result = BatchCommitResult(0, 0, 0, 0, 0)
        self._result_lock = Lock()

    def start(self) -> None:
        if self._started:
            return
        if self._closed:
            raise RuntimeError("bounded writer cannot be restarted after close")
        self._started = True
        self._thread.start()

    async def submit(self, rows: list[IncomingListing]) -> None:
        if not self._started:
            raise RuntimeError("start the bounded writer before submit")
        for row in rows:
            await self._put(row)

    async def flush(self) -> BatchCommitResult:
        if not self._started:
            return self.snapshot()
        self._raise_if_failed()
        done = Event()
        await self._put(_Flush(done))
        await asyncio.to_thread(done.wait)
        self._raise_if_failed()
        return self.snapshot()

    async def aclose(self) -> BatchCommitResult:
        if self._closed:
            self._raise_if_failed()
            return self.snapshot()
        self._closed = True
        if not self._started:
            return self.snapshot()
        done = Event()
        await self._put(_Stop(done))
        await asyncio.to_thread(done.wait)
        await asyncio.to_thread(self._thread.join)
        self._raise_if_failed()
        return self.snapshot()

    def snapshot(self) -> BatchCommitResult:
        with self._result_lock:
            return self._result

    async def _put(self, value: IncomingListing | _Flush | _Stop) -> None:
        while True:
            self._raise_if_failed()
            try:
                self._queue.put_nowait(value)
                return
            except Full:
                await asyncio.sleep(0.005)

    def _run(self) -> None:
        batch: list[IncomingListing] = []
        session = self._session_factory()
        writer = ListingBatchWriter(session)
        deadline = monotonic() + self._flush_seconds
        try:
            while True:
                timeout = max(0.0, deadline - monotonic())
                try:
                    item = self._queue.get(timeout=timeout)
                except Empty:
                    self._commit(writer, batch)
                    batch.clear()
                    deadline = monotonic() + self._flush_seconds
                    continue

                if isinstance(item, IncomingListing):
                    batch.append(item)
                    if len(batch) >= self._batch_size:
                        self._commit(writer, batch)
                        batch.clear()
                        deadline = monotonic() + self._flush_seconds
                    continue

                self._commit(writer, batch)
                batch.clear()
                deadline = monotonic() + self._flush_seconds
                item.done.set()
                if isinstance(item, _Stop):
                    return
        except BaseException as error:
            self._failure = error
            try:
                session.rollback()
            finally:
                self._unblock_controls()
        finally:
            session.close()

    def _commit(self, writer: ListingBatchWriter, batch: list[IncomingListing]) -> None:
        if not batch:
            return
        result = writer.commit_batch(self._job_id, batch)
        with self._result_lock:
            current = self._result
            self._result = BatchCommitResult(
                fetched_count=current.fetched_count + result.fetched_count,
                committed_count=current.committed_count + result.committed_count,
                created_count=current.created_count + result.created_count,
                updated_count=current.updated_count + result.updated_count,
                rejected_count=current.rejected_count + result.rejected_count,
            )

    def _unblock_controls(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                return
            if isinstance(item, (_Flush, _Stop)):
                item.done.set()

    def _raise_if_failed(self) -> None:
        if self._failure is not None:
            raise RuntimeError("bounded DB writer failed") from self._failure
