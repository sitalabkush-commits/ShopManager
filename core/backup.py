"""Consistent daily backups using SQLite's online backup API (safe while the app is running)."""
from __future__ import annotations
import hashlib, logging, os, sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from . import db

log = logging.getLogger(__name__)
BACKUP_DIR = db.BASE_DIR / "backups"
KEEP_LAST = 14


class CloudProvider(ABC):
    """Implement upload() for S3 / Drive / etc. and register it with register_cloud_hook()."""
    @abstractmethod
    def upload(self, path: Path) -> None: ...


_hooks: list[CloudProvider] = []


def register_cloud_hook(p: CloudProvider) -> None:
    _hooks.append(p)


def make_backup(force: bool = False) -> Path | None:
    """Create backups/shop_YYYYMMDD_HHMMSS.db (+ .sha256). Returns None if today's already exists."""
    BACKUP_DIR.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    if not force and any(BACKUP_DIR.glob(f"shop_{today}_*.db")):
        return None
    final = BACKUP_DIR / f"shop_{datetime.now():%Y%m%d_%H%M%S}.db"
    tmp = final.with_suffix(".tmp")
    src, dst = sqlite3.connect(db.DB_PATH), sqlite3.connect(tmp)
    try:
        src.backup(dst)                                   # consistent snapshot
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup failed integrity check")
    except Exception:
        dst.close(); src.close(); tmp.unlink(missing_ok=True)
        raise
    dst.close(); src.close()
    os.replace(tmp, final)
    digest = hashlib.sha256(final.read_bytes()).hexdigest()
    (final.parent / (final.name + ".sha256")).write_text(f"{digest}  {final.name}\n")
    try:
        os.chmod(final, 0o600)                            # owner-only (best effort on Windows)
    except OSError:
        pass
    _prune()
    for h in _hooks:                                      # a failing cloud hook never breaks local backup
        try:
            h.upload(final)
        except Exception:
            log.exception("Cloud hook failed")
    return final


def _prune() -> None:
    files = sorted(BACKUP_DIR.glob("shop_*.db"))
    for f in files[:-KEEP_LAST]:
        f.unlink(missing_ok=True)
        (f.parent / (f.name + ".sha256")).unlink(missing_ok=True)
