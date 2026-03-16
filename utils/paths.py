import os, warnings
from pathlib import Path

def is_windows_mount(path: str) -> bool:
    p = Path(path).resolve()
    return len(p.parts) >= 3 and p.parts[1] == "mnt" and len(p.parts[2]) == 1

def normalize_path(raw: str) -> str:
    if len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha():
        drive = raw[0].lower()
        rest  = raw[2:].replace("\\","/")
        path  = f"/mnt/{drive}{rest}"
        warnings.warn(f"Windows path mapped: {raw} → {path}\n"
                      f"Move data to ~/data/ for 10-50x better I/O.", UserWarning, stacklevel=3)
        return path
    return raw.replace("\\","/")

def get_watch_folder() -> Path:
    import yaml
    cfg = yaml.safe_load(open("config.yaml"))
    raw = cfg["knowledge_base"]["watch_folder"]
    raw = os.path.expandvars(raw)
    raw = os.path.expanduser(raw)
    path = Path(normalize_path(raw))
    path.mkdir(parents=True, exist_ok=True)
    return path
