"""Run work in a background thread; progress and results come back on the Tk thread."""
from __future__ import annotations

import queue
import threading

from um import dragon_log


class Cancelled(Exception):
    """Raised by a task that the user cancelled; it is reported quietly, not logged as a failure."""


class TaskRunner:
    def __init__(self, root):
        self.root = root
        self.queue: queue.Queue = queue.Queue()
        self.active = 0
        self.listeners = []
        self._polling = False

    @property
    def busy(self) -> bool:
        return self.active > 0

    def on_change(self, callback) -> None:
        """callback(is_busy) runs whenever a task starts or the last one ends."""
        self.listeners.append(callback)

    def run(self, work, on_done=None, on_error=None, on_progress=None, label: str = 'Task') -> None:
        """work(progress) runs in a thread; on_done(result) / on_error(exc) / on_progress(item) run on the Tk thread."""
        self.active += 1
        self._notify()

        def target():
            def progress(item):
                self.queue.put(('progress', on_progress, item))
            try:
                result = work(progress)
            except Cancelled as exc:
                self.queue.put(('error', on_error, exc))
            except Exception as exc:  # noqa: BLE001 - every failure is shown to the user and logged
                dragon_log.log_exception(f'{label} failed', exc)
                self.queue.put(('error', on_error, exc))
            else:
                self.queue.put(('done', on_done, result))
        threading.Thread(target=target, daemon=True).start()
        self._schedule()

    def _schedule(self) -> None:
        if not self._polling:
            self._polling = True
            self.root.after(60, self._poll)

    def _poll(self) -> None:
        self._polling = False
        try:
            while True:
                kind, callback, payload = self.queue.get_nowait()
                if kind == 'progress':
                    if callback:
                        callback(payload)
                    continue
                self.active -= 1
                try:
                    if callback:
                        callback(payload)
                finally:
                    self._notify()
        except queue.Empty:
            pass
        if self.active > 0:
            self._schedule()

    def _notify(self) -> None:
        for callback in list(self.listeners):
            try:
                callback(self.busy)
            except Exception as exc:  # noqa: BLE001 - a widget that is gone must not break the others
                dragon_log.get_logger().debug('busy listener failed: %s', exc)
