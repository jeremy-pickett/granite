"""
Thin database helpers shared by all collectors.
Every collector talks to the same Postgres instance through these functions.
"""

import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from config import DATABASE_URL


@contextmanager
def get_conn():
    """Yield a connection that auto-commits on clean exit, rolls back on error."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── securities ────────────────────────────────────────────────────────

def get_securities(security_type=None):
    """Return list of dicts: {security_id, ticker, name, security_type}."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if security_type:
                cur.execute(
                    "SELECT security_id, ticker, name, security_type "
                    "FROM securities WHERE security_type = %s ORDER BY ticker",
                    (security_type,),
                )
            else:
                cur.execute(
                    "SELECT security_id, ticker, name, security_type "
                    "FROM securities ORDER BY ticker"
                )
            return cur.fetchall()


# ── collector bookkeeping ─────────────────────────────────────────────

def collector_start(collector_id):
    """Mark a collector run as started."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE collectors SET last_run_at = now() WHERE collector_id = %s",
                (collector_id,),
            )


def collector_success(collector_id, records_total, securities_covered, total_securities):
    """Mark a collector run as succeeded and update coverage stats."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            pct = round(securities_covered / total_securities * 100, 2) if total_securities else 0
            cur.execute(
                """UPDATE collectors
                   SET last_success_at   = now(),
                       last_error        = NULL,
                       records_total     = %s,
                       securities_covered = %s,
                       total_securities  = %s,
                       coverage_pct      = %s
                   WHERE collector_id = %s""",
                (records_total, securities_covered, total_securities, pct, collector_id),
            )


def collector_error(collector_id, error_msg):
    """Record a collector failure."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE collectors SET last_error = %s WHERE collector_id = %s",
                (str(error_msg)[:500], collector_id),
            )


# ── collector_coverage upsert ─────────────────────────────────────────

def upsert_coverage(collector_id, security_id, records_count):
    """Update or insert a coverage row for one security."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO collector_coverage (collector_id, security_id, records_count, last_data_at)
                   VALUES (%s, %s, %s, now())
                   ON CONFLICT (collector_id, security_id)
                   DO UPDATE SET records_count = collector_coverage.records_count + EXCLUDED.records_count,
                                 last_data_at  = now()""",
                (collector_id, security_id, records_count),
            )


def upsert_coverage_batch(collector_id, rows):
    """Batch upsert coverage. rows = list of (security_id, records_count)."""
    if not rows:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            values = [(collector_id, sid, cnt) for sid, cnt in rows]
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO collector_coverage (collector_id, security_id, records_count, last_data_at)
                   VALUES %s
                   ON CONFLICT (collector_id, security_id)
                   DO UPDATE SET records_count = collector_coverage.records_count + EXCLUDED.records_count,
                                 last_data_at  = now()""",
                values,
                template="(%s, %s, %s, now())",
            )
