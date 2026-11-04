from concurrent.futures import ThreadPoolExecutor, wait
from threading import BoundedSemaphore
from time import monotonic

PROBE_SECONDS = 1.0


def before_deadline(completed_at, deadline):
    return completed_at < deadline


class HealthService:
    def __init__(self, mysql, qdrant, draining, *, clock=monotonic):
        self.probes = {"mysql": mysql, "qdrant": qdrant}
        self.draining = draining
        self.clock = clock
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="health")
        self.slots = {name: BoundedSemaphore(2) for name in self.probes}

    def sample(self):
        deadline = self.clock() + PROBE_SECONDS
        states = dict.fromkeys(self.probes, "unavailable")
        futures = {}
        for name, probe in self.probes.items():
            slot = self.slots[name]
            if slot.acquire(blocking=False):
                future = self.executor.submit(self._run, probe)
                future.add_done_callback(lambda _, acquired=slot: acquired.release())
                futures[future] = name

        done, pending = wait(futures, timeout=max(0, deadline - self.clock()))
        for future in pending:
            future.cancel()
        for future in done:
            ready, completed_at = future.result()
            if ready and before_deadline(completed_at, deadline):
                states[futures[future]] = "ready"

        if self.draining() or states["mysql"] == "unavailable":
            return 503, "not_ready", states
        if states["qdrant"] == "unavailable":
            return 200, "degraded", states
        return 200, "ready", states

    def _run(self, probe):
        try:
            ready = probe()
        except Exception:
            ready = False
        return ready, self.clock()
