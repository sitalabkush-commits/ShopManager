"""OCR providers + staging-bucket persistence. Nothing touches products until commit()."""
from __future__ import annotations
import json, re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from . import db

FIELDS = ("barcode", "name", "qty", "cost", "price", "tax_rate")


def _f(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return 0.0


def normalise(d: dict) -> dict:
    return {"barcode": str(d.get("barcode", "") or "").strip(), "name": str(d.get("name", "")).strip(),
            "qty": _f(d.get("qty", 1)) or 1.0, "cost": _f(d.get("cost", 0)),
            "price": _f(d.get("price", 0)), "tax_rate": _f(d.get("tax_rate", 0))}


class OcrProvider(ABC):
    @abstractmethod
    def parse(self, path: str) -> list[dict]: ...


class TesseractProvider(OcrProvider):
    """Offline default: expects lines like 'Item name  qty  rate'. Review in staging anyway."""
    LINE = re.compile(r"^(?P<name>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+(?P<cost>\d+(?:\.\d+)?)\s*$")

    def parse(self, path: str) -> list[dict]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as e:
            raise RuntimeError("pip install pytesseract pillow, and install the Tesseract binary") from e
        rows = []
        for line in pytesseract.image_to_string(Image.open(path)).splitlines():
            m = self.LINE.match(line.strip())
            if m:
                rows.append(normalise(m.groupdict()))
        return rows


class VisionLLMProvider(OcrProvider):
    """Plug any vision model: call_model(image_bytes, prompt) -> str (JSON)."""
    PROMPT = ('Extract line items from this purchase invoice. Reply with JSON only: '
              '{"items":[{"barcode":"","name":"","qty":0,"cost":0,"price":0,"tax_rate":0}]}')

    def __init__(self, call_model):
        self.call_model = call_model

    def parse(self, path: str) -> list[dict]:
        raw = self.call_model(Path(path).read_bytes(), self.PROMPT).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return [normalise(x) for x in json.loads(raw)["items"]]


_provider: OcrProvider = TesseractProvider()


def set_provider(p: OcrProvider) -> None:
    global _provider
    _provider = p


def get_provider() -> OcrProvider:
    return _provider


# ---- staging bucket (persisted, so a crash/restart doesn't lose a scan)
def stage_rows(rows: list[dict], source: str) -> None:
    now = datetime.now().strftime(db.FMT)
    with db.tx() as c:
        for r in rows:
            r = normalise(r)
            c.execute("INSERT INTO ocr_staging(source,barcode,name,qty,cost,price,tax_rate,created_at)"
                      " VALUES(?,?,?,?,?,?,?,?)", (source, r["barcode"], r["name"], r["qty"],
                                                   r["cost"], r["price"], r["tax_rate"], now))


def load_staging():
    return db.conn().execute("SELECT * FROM ocr_staging ORDER BY id").fetchall()


def add_blank() -> None:
    stage_rows([{"name": "", "qty": 1}], "manual")


def update_field(row_id: int, field: str, value) -> None:
    if field not in FIELDS:
        raise ValueError(field)
    db.conn().execute(f"UPDATE ocr_staging SET {field}=? WHERE id=?", (value, row_id))


def delete_rows(ids: list[int]) -> None:
    with db.tx() as c:
        c.executemany("DELETE FROM ocr_staging WHERE id=?", [(i,) for i in ids])


def discard_all() -> None:
    db.conn().execute("DELETE FROM ocr_staging")


def commit(rows: list[dict]) -> int:
    """Atomically upsert verified rows into products (stock += qty) and clear them from staging."""
    with db.tx() as c:
        for r in rows:
            p = c.execute("SELECT id FROM products WHERE barcode=? AND barcode<>''", (r["barcode"],)).fetchone() \
                if r["barcode"] else None
            p = p or c.execute("SELECT id FROM products WHERE name=? COLLATE NOCASE", (r["name"],)).fetchone()
            if p:
                c.execute("UPDATE products SET stock=stock+?, cost=?, tax_rate=?, "
                          "price=CASE WHEN ?>0 THEN ? ELSE price END WHERE id=?",
                          (r["qty"], r["cost"], r["tax_rate"], r["price"], r["price"], p["id"]))
            else:
                c.execute("INSERT INTO products(barcode,name,price,cost,stock,tax_rate) VALUES(?,?,?,?,?,?)",
                          (r["barcode"], r["name"], r["price"], r["cost"], r["qty"], r["tax_rate"]))
            c.execute("DELETE FROM ocr_staging WHERE id=?", (r["id"],))
    return len(rows)
