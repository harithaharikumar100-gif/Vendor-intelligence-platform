"""Bounded workers with persistent requests and renewable, recoverable execution leases."""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor


class JobRunner:
    def __init__(self, store, execute, concurrency=2, lease_seconds=120):
        self.store, self.execute = store, execute
        self.lease_seconds = lease_seconds
        self.pool = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix='vendor-job')
        self.slots = threading.BoundedSemaphore(concurrency)
        self.stop = threading.Event()
        self.thread = None

    def submit(self, job_id):
        if not self.slots.acquire(blocking=False):
            return False
        lease = {'worker': uuid.uuid4().hex}
        key = f'lease:{job_id}'
        try:
            claimed = self.store.try_claim(key, lease, ttl_seconds=self.lease_seconds)
        except Exception:
            self.slots.release()
            raise
        if not claimed:
            self.slots.release()
            return False
        self.pool.submit(self._run, job_id, key, lease)
        return True

    def _run(self, job_id, key, lease):
        done = threading.Event()
        def heartbeat():
            while not done.wait(self.lease_seconds / 3):
                if not self.store.renew_claim(key, lease, self.lease_seconds):
                    return
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            job = self.store.get_json(f'job:{job_id}')
            if job and job.get('status') in ('pending', 'running'):
                self.execute(job, self.store, lambda: self.store.get_json(key) == lease)
        finally:
            done.set()
            thread.join(timeout=1)
            self.store.release_claim(key, lease)
            self.slots.release()

    def recover(self):
        for key in self.store.keys('job:'):
            job = self.store.get_json(key)
            if job and job.get('status') in ('pending', 'running') and job.get('request'):
                self.submit(job['job_id'])

    def start(self):
        if self.thread is not None:
            return
        def monitor():
            while not self.stop.is_set():
                try:
                    self.recover()
                except Exception:
                    # Keep the monitor alive during a transient store outage; no job is marked successful.
                    pass
                self.stop.wait(2)
        self.thread = threading.Thread(target=monitor, daemon=True, name='vendor-job-recovery')
        self.thread.start()

    def shutdown(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
        self.pool.shutdown(wait=True)
