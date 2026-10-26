"""The What-If worker: claims accepted runs and answers them (forked from the Cockpit's worker).

Runs are claimed with compare-and-swap, so two workers never answer one run.
A run left RUNNING by a stopped service is failed visibly on start
(`Store.recover`), never left hanging.
"""
from __future__ import annotations

import threading
import time

from backend.whatif_v5.chat import orchestrator


class Worker:
    def __init__(self, store, threads: int = 2):
        self.store = store
        self.n = threads
        self.stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self.store.recover()
        for i in range(self.n):
            t = threading.Thread(target=self.serve_forever, name=f"whatif-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def serve_forever(self) -> None:
        while not self.stop.is_set():
            run = self.store.claim_next()
            if run is None:
                time.sleep(0.05)
                continue
            orchestrator.answer(self.store, run["run_id"])

    def drain(self, timeout: float = 60.0) -> None:
        """Answer every accepted run now, in this thread (tests)."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            run = self.store.claim_next()
            if run is None:
                return
            orchestrator.answer(self.store, run["run_id"])
