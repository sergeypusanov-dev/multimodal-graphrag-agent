import os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

def is_windows_mount(path: str) -> bool:
    p = Path(path).resolve()
    return len(p.parts) >= 3 and p.parts[1] == "mnt" and len(p.parts[2]) == 1

def get_observer(watch_path: str):
    force = os.getenv("WATCHDOG_POLLING", "false").lower() == "true"
    if force or is_windows_mount(watch_path):
        import logging
        logging.warning(f"PollingObserver for {watch_path}. Move data to ~/data/ for best perf.")
        return PollingObserver(timeout=5)
    return Observer()

class KnowledgeEventHandler(FileSystemEventHandler):
    def __init__(self, supported_extensions: set):
        self.supported = supported_extensions
        self._pending: dict[str, float] = {}

    def on_created(self, event):
        if not event.is_directory: self._handle(event.src_path)

    def on_modified(self, event):
        if not event.is_directory: self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory: self._handle(event.dest_path)

    def _handle(self, path: str):
        import time
        from tasks.watcher import index_document
        if Path(path).suffix.lower() not in self.supported: return
        now = time.time()
        if now - self._pending.get(path, 0) < 2.0: return
        self._pending[path] = now
        index_document.apply_async(args=[path], queue="indexing")
