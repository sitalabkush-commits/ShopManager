"""SQLite data layer: schema, per-thread connections, 30-day retention/archive, reports."""
from __future__ import annotations
import hashlib, hmac, os, sqlite3, threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("SHOP_DB", BASE_DIR / "shop.db"))
RETENTION_DAYS = 30
FMT = "%Y-%m-%d %H:%M:%S"
_local = threading.local()

_INV = """({pk}, invoice_no TEXT, date TEXT NOT NULL, customer TEXT DEFAULT '',
 subtotal REAL DEFAULT 0, tax REAL DEFAULT 0, total REAL DEFAULT 0,
 profit REAL DEFAULT 0, units REAL DEFAULT 0, payment TEXT DEFAULT 'Cash')"""
_ITM = """({pk}, invoice_id INTEGER NOT NULL, product_id INTEGER, name TEXT,
 qty REAL, price REAL, cost REAL DEFAULT 0, tax_rate REAL DEFAULT 0)"""
_AUTO, _PLAIN = "id INTEGER PRIMARY KEY AUTOINCREMENT", "id INTEGER PRIMARY KEY"

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT,
       barcode TEXT DEFAULT '', name TEXT NOT NULL DEFAULT '', price REAL DEFAULT 0,
       cost REAL DEFAULT 0, stock REAL DEFAULT 0, tax_rate REAL DEFAULT 0)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_prod_barcode ON products(barcode) WHERE barcode <> ''",
    "CREATE INDEX IF NOT EXISTS ix_prod_name ON products(name)",
    "CREATE TABLE IF NOT EXISTS invoices " + _INV.format(pk=_AUTO),
    "CREATE TABLE IF NOT EXISTS invoice_items " + _ITM.format(pk=_AUTO),
    "CREATE TABLE IF NOT EXISTS invoices_archive " + _INV.format(pk=_PLAIN),
    "CREATE TABLE IF NOT EXISTS invoice_items_archive " + _ITM.format(pk=_PLAIN),
    "CREATE INDEX IF NOT EXISTS ix_inv_date ON invoices(date)",
    "CREATE INDEX IF NOT EXISTS ix_items_inv ON invoice_items(invoice_id)",
    "CREATE INDEX IF NOT EXISTS ix_arch_date ON invoices_archive(date)",
    "CREATE INDEX IF NOT EXISTS ix_arch_no ON invoices_archive(invoice_no)",
    "CREATE INDEX IF NOT EXISTS ix_arch_items_inv ON invoice_items_archive(invoice_id)",
    "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)",
    """CREATE TABLE IF NOT EXISTS ocr_staging (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT,
       barcode TEXT DEFAULT '', name TEXT DEFAULT '', qty REAL DEFAULT 1, cost REAL DEFAULT 0,
       price REAL DEFAULT 0, tax_rate REAL DEFAULT 0, created_at TEXT)""",
]


def conn() -> sqlite3.Connection:
    """One connection per thread (sqlite3 objects must not cross threads). Autocommit mode."""
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        for p in ("journal_mode=WAL", "synchronous=NORMAL", "temp_store=MEMORY", "foreign_keys=ON"):
            c.execute(f"PRAGMA {p}")
        _local.c = c
    return c


def close_conn() -> None:
    c = getattr(_local, "c", None)
    if c:
        c.close()
        _local.c = None


@contextmanager
def tx():
    c = conn()
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise


def _ensure_columns(table: str, cols: dict[str, str]) -> None:
    have = {r["name"] for r in conn().execute(f"PRAGMA table_info({table})")}
    for name, ddl in cols.items():
        if name not in have:
            conn().execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db() -> None:
    c = conn()
    for stmt in SCHEMA:
        c.execute(stmt)
    # Migrate a pre-existing schema that lacks newer columns.
    _ensure_columns("invoices", {"invoice_no": "TEXT", "units": "REAL DEFAULT 0",
                                 "payment": "TEXT DEFAULT 'Cash'", "profit": "REAL DEFAULT 0"})
    _ensure_columns("products", {"cost": "REAL DEFAULT 0", "tax_rate": "REAL DEFAULT 0"})


def cutoff(days: int = RETENTION_DAYS) -> str:
    return (datetime.now() - timedelta(days=days)).strftime(FMT)


# ---------------------------------------------------------------- products
def get_product_by_barcode(code: str):
    return conn().execute("SELECT * FROM products WHERE barcode = ?", (code.strip(),)).fetchone()


def search_products(term: str, limit: int = 20):
    like = f"%{term.strip()}%"
    return conn().execute("SELECT * FROM products WHERE name LIKE ? OR barcode LIKE ? "
                          "ORDER BY name LIMIT ?", (like, like, limit)).fetchall()


# ---------------------------------------------------------------- billing
def save_invoice(cart: list[dict], customer: str = "", payment: str = "Cash") -> str:
    """cart item: {product_id, name, qty, price, cost, tax_rate}. Atomic: invoice + items + stock."""
    if not cart:
        raise ValueError("Cart is empty")
    sub = sum(i["qty"] * i["price"] for i in cart)
    tax = sum(i["qty"] * i["price"] * i["tax_rate"] / 100 for i in cart)
    profit = sum(i["qty"] * (i["price"] - i["cost"]) for i in cart)
    units = sum(i["qty"] for i in cart)
    with tx() as c:
        cur = c.execute(
            "INSERT INTO invoices(date,customer,subtotal,tax,total,profit,units,payment) VALUES(?,?,?,?,?,?,?,?)",
            (datetime.now().strftime(FMT), customer, round(sub, 2), round(tax, 2),
             round(sub + tax, 2), round(profit, 2), units, payment))
        iid = cur.lastrowid
        no = f"INV-{iid:06d}"
        c.execute("UPDATE invoices SET invoice_no=? WHERE id=?", (no, iid))
        for i in cart:
            c.execute("INSERT INTO invoice_items(invoice_id,product_id,name,qty,price,cost,tax_rate)"
                      " VALUES(?,?,?,?,?,?,?)", (iid, i["product_id"], i["name"], i["qty"],
                                                 i["price"], i["cost"], i["tax_rate"]))
            c.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (i["qty"], i["product_id"]))
    return no


# ---------------------------------------------------------------- history + archive
def search_invoices(term: str = "", include_archive: bool = False, limit: int = 500):
    """Default = last 30 days only (indexed on date). Archive is touched only on request."""
    like = f"%{term.strip()}%"
    sql = ("SELECT *, 'Active' AS source FROM invoices "
           "WHERE date >= ? AND (invoice_no LIKE ? OR customer LIKE ?)")
    params: list = [cutoff(), like, like]
    if include_archive:
        sql += (" UNION ALL SELECT *, 'Archive' AS source FROM invoices_archive "
                "WHERE invoice_no LIKE ? OR customer LIKE ?")
        params += [like, like]
    return conn().execute(sql + " ORDER BY date DESC LIMIT ?", params + [limit]).fetchall()


def invoice_items(invoice_id: int, archived: bool = False):
    t = "invoice_items_archive" if archived else "invoice_items"
    return conn().execute(f"SELECT * FROM {t} WHERE invoice_id = ?", (invoice_id,)).fetchall()


def archive_old(days: int = RETENTION_DAYS) -> int:
    """Move invoices (+items) older than `days` into archive tables in ONE transaction."""
    cut = cutoff(days)
    ids = "SELECT id FROM invoices WHERE date < ?"
    with tx() as c:
        c.execute(f"INSERT OR IGNORE INTO invoice_items_archive SELECT * FROM invoice_items "
                  f"WHERE invoice_id IN ({ids})", (cut,))
        c.execute("INSERT OR IGNORE INTO invoices_archive SELECT * FROM invoices WHERE date < ?", (cut,))
        c.execute(f"DELETE FROM invoice_items WHERE invoice_id IN ({ids})", (cut,))
        n = c.execute("DELETE FROM invoices WHERE date < ?", (cut,)).rowcount
    if n:
        conn().execute("PRAGMA optimize")
    return n


# ---------------------------------------------------------------- reports
def monthly_summary(months: int = 12):
    y, m = datetime.now().year, datetime.now().month - (months - 1)
    while m < 1:
        m += 12; y -= 1
    start = f"{y:04d}-{m:02d}-01 00:00:00"
    return conn().execute("""
        SELECT strftime('%Y-%m', date) AS month, COUNT(*) AS invoices, SUM(units) AS units,
               SUM(total) AS revenue, SUM(tax) AS tax, SUM(profit) AS profit
        FROM (SELECT date,units,total,tax,profit FROM invoices
              UNION ALL SELECT date,units,total,tax,profit FROM invoices_archive)
        WHERE date >= ? GROUP BY strftime('%Y-%m', date) ORDER BY month DESC""", (start,)).fetchall()


# ---------------------------------------------------------------- settings / admin PIN
def get_setting(key: str, default: str = "") -> str:
    r = conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key: str, value: str) -> None:
    conn().execute("INSERT INTO settings(key,value) VALUES(?,?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def _hash(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()


def has_pin() -> bool:
    return bool(get_setting("admin_pin"))


def set_pin(pin: str) -> None:
    salt = os.urandom(16).hex()
    set_setting("admin_pin", f"{salt}${_hash(pin, salt)}")


def verify_pin(pin: str) -> bool:
    stored = get_setting("admin_pin")
    if "$" not in stored:
        return False
    salt, h = stored.split("$", 1)
    return hmac.compare_digest(h, _hash(pin, salt))
