import os, hashlib, yaml
from celery import Celery
from celery.schedules import crontab
from pathlib import Path

config = yaml.safe_load(open("config.yaml"))
app    = Celery("agent",
                broker=os.getenv("REDIS_URL","redis://localhost:6379/0"),
                backend=os.getenv("REDIS_URL","redis://localhost:6379/0"))

app.conf.task_queues = (
    __import__("kombu").Queue("indexing", routing_key="indexing"),
    __import__("kombu").Queue("default",  routing_key="default"),
)
app.conf.task_default_queue         = "default"
app.conf.worker_prefetch_multiplier = 1
app.conf.task_acks_late             = True

schedule_str = config["knowledge_base"]["sync_schedule"]
parts = schedule_str.split()
app.conf.beat_schedule = {
    "sync-knowledge-base": {
        "task":     "tasks.watcher.sync_knowledge_folder",
        "schedule": crontab(minute=parts[0], hour=parts[1]),
    },
}

def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda: f.read(8192), b""): h.update(chunk)
    return h.hexdigest()

@app.task(name="tasks.watcher.sync_knowledge_folder", bind=True, max_retries=3, default_retry_delay=60)
def sync_knowledge_folder(self):
    from utils.paths import get_watch_folder
    from database import get_db
    db = get_db()
    supported = set()
    for exts in config["knowledge_base"]["supported_formats"].values():
        supported.update(exts)
    watch_folder = get_watch_folder()
    new_files, changed_files = [], []
    for file_path in watch_folder.rglob("*"):
        if not file_path.is_file(): continue
        if file_path.suffix.lower() not in supported: continue
        max_mb = config["knowledge_base"]["max_file_size_mb"]
        if file_path.stat().st_size > max_mb * 1024 * 1024: continue
        fp_str  = str(file_path)
        indexed = db.fetchone("SELECT file_hash FROM kg_file_index WHERE file_path=%s",[fp_str])
        if not indexed:
            new_files.append(fp_str)
        elif _file_hash(fp_str) != indexed["file_hash"]:
            changed_files.append(fp_str)
    for f in new_files + changed_files:
        index_document.apply_async(args=[f], queue="indexing")
    return {"new":len(new_files),"changed":len(changed_files)}

@app.task(name="tasks.watcher.index_document", bind=True, max_retries=3,
          default_retry_delay=120, queue="indexing", time_limit=3600)
def index_document(self, file_path: str):
    from media.processor import process_file
    from graph.indexer import run_indexing_pipeline
    from database import get_db
    db = get_db()
    try:
        db.execute("""
            INSERT INTO kg_file_index (file_path,file_hash,last_modified,status)
            VALUES (%s,%s,NOW(),'processing')
            ON CONFLICT (file_path) DO UPDATE SET status='processing',indexed_at=NOW()
        """,[file_path,_file_hash(file_path)])
        result = process_file(file_path, config)
        stats  = run_indexing_pipeline(file_path, result, config, db)
        db.execute("""
            UPDATE kg_file_index SET file_hash=%s,status='indexed',
              entity_count=%s,chunk_count=%s,error_msg=NULL WHERE file_path=%s
        """,[_file_hash(file_path),stats["entities"],stats["chunks"],file_path])
    except Exception as exc:
        db.execute("UPDATE kg_file_index SET status='failed',error_msg=%s WHERE file_path=%s",
                   [str(exc)[:500],file_path])
        raise self.retry(exc=exc)
