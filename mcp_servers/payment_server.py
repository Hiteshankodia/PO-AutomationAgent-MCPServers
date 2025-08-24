import sys, pathlib
root = pathlib.Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

"""Payment calculation MCP server (pymssql + .env loader + lazy DB + robust ID handling + static mapping)."""
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Load .env from project root so this separate MCP process gets DB_* vars
load_dotenv(dotenv_path=root / ".env")
load_dotenv()

mcp = FastMCP("PaymentService")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------- Lazy DB wiring ----------
_DB_SOURCE = None
_db_obj = None

_REQUIRED_ENV = ("DB_SERVER", "DB_DATABASE", "DB_USERNAME", "DB_PASSWORD")

def _missing_env() -> List[str]:
    return [k for k in _REQUIRED_ENV if not os.getenv(k)]

def _get_db():
    """
    Create the DB object on first use; never at import time.
    Verify env first so we can surface a clean error message via the tool result.
    """
    global _db_obj, _DB_SOURCE
    if _db_obj is not None:
        return _db_obj

    missing = _missing_env()
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    # NOTE: this must be your pymssql variant
    from database.db_operations import DatabaseManager
    _db_obj = DatabaseManager()
    _DB_SOURCE = "DatabaseManager(pymssql)"
    logger.info("PaymentService DB source: %s", _DB_SOURCE)
    return _db_obj


def _fetch_all(sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    """
    Execute a SELECT and return rows as list[dict] using DatabaseManager.get_connection().
    """
    db = _get_db()
    with db.get_connection() as conn:
        cursor = conn.cursor(as_dict=True)
        cursor.execute(sql, params or ())
        rows = cursor.fetchall() or []
        return rows


def _fetch_one(sql: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
    rows = _fetch_all(sql, params)
    return rows[0] if rows else None


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _lerp(v: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y0
    t = (v - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


# ---------- Helpers: PO id normalization & existence checks ----------

def _looks_like_request_code(po_ref: Union[int, str]) -> bool:
    """
    Detects request-style IDs like 'PO-20250822151755' or an integer timestamp-ish 20250822151755.
    These are *not* DB primary keys for PurchaseOrders.po_id in your schema (which are 1..N).
    """
    try:
        if isinstance(po_ref, str) and po_ref.strip().upper().startswith("PO-"):
            return True
        if int(po_ref) > 10_000_000:  # heuristic (e.g., yyyymmddHHMMSS)
            return True
    except Exception:
        pass
    return False

# ---------- Static mapping for demo POs ----------
# Map supplier_id deterministically to the static demo DB po_id 1..4
_STATIC_PO_MAP: Dict[str, int] = {
    "SUP001": 1,
    "SUP002": 2,
    "SUP003": 3,
    "SUP999": 4,
}

def _map_request_to_po(po_ref: Union[int, str], supplier_id: Optional[str] = None) -> Optional[int]:
    """
    For demo purposes, map request-style IDs (PO-...) or large timestamps
    back to static DB po_id values (1..4) using supplier_id. If po_ref is already
    an int (1..N), returns it as-is.
    """
    # If it's already a small-ish integer, just use it
    try:
        as_int = int(po_ref)
        return as_int
    except Exception:
        pass

    # If it looks like a request code / timestamp-ish and a supplier_id is provided, map it
    if _looks_like_request_code(po_ref) and supplier_id:
        sid = supplier_id.strip().upper()
        pid = _STATIC_PO_MAP.get(sid)
        if pid:
            return pid

    # Unable to resolve
    return None


def _po_exists(db_po_id: int) -> bool:
    row = _fetch_one("SELECT 1 AS ok FROM PurchaseOrders WHERE po_id = %s", (db_po_id,))
    return bool(row)


# ---------- Core computations ----------

def _compute_base_po_amount(po_id: int) -> Dict[str, Any]:
    """
    Total PO Amount = Σ(quantity * unit_price) + tax_amount + logistic_cost
    Tables:
      - PurchaseOrderItems(po_id, quantity, unit_price)
      - PurchaseOrders(po_id, supplier_id, currency, exchange_rate, tax_amount, logistic_cost)
    """
    line_q = """
    SELECT COALESCE(SUM(CAST(quantity AS FLOAT) * CAST(unit_price AS FLOAT)), 0) AS line_total
    FROM PurchaseOrderItems
    WHERE po_id = %s
    """
    head_q = """
    SELECT po_id, supplier_id,
           currency, exchange_rate,
           COALESCE(CAST(tax_amount AS FLOAT), 0)        AS tax_amount,
           COALESCE(CAST(logistic_cost AS FLOAT), 0)     AS freight_amount
    FROM PurchaseOrders
    WHERE po_id = %s
    """

    line_row = _fetch_one(line_q, (po_id,)) or {}
    head_row = _fetch_one(head_q, (po_id,)) or {}

    if not head_row:
        return {"error": True, "message": f"PO {po_id} not found"}

    line_total = _safe_float(line_row.get("line_total"))
    tax_amt = _safe_float(head_row.get("tax_amount"))
    freight_amt = _safe_float(head_row.get("freight_amount"))
    ex_rate = _safe_float(head_row.get("exchange_rate", 1.0), 1.0)

    total_base = line_total + tax_amt + freight_amt
    total_in_inr = total_base * ex_rate

    return {
        "error": False,
        "po_id": po_id,
        "supplier_id": head_row.get("supplier_id"),
        "currency": head_row.get("currency", "INR"),
        "exchange_rate": ex_rate,
        "line_total": round(line_total, 2),
        "tax_amount": round(tax_amt, 2),
        "freight_amount": round(freight_amt, 2),
        "total_po_amount": round(total_base, 2),
        "total_in_inr": round(total_in_inr, 2),
    }


def _risk_band(score: float) -> str:
    if score >= 80: return "LOW"
    if score >= 60: return "MEDIUM"
    if score >= 40: return "HIGH"
    return "VERY_HIGH"


def _upfront_percent(score: float) -> float:
    """
    Policy:
      LOW (80–100)    -> 100%
      MED (60–79)     -> 70–85% (linear)
      HIGH (40–59)    -> 40–60% (linear)
      VERY_HIGH (<40) -> 0–30%  (linear)
    """
    s = _clamp(score, 0, 100)
    if s >= 80: return 100.0
    if s >= 60: return _lerp(s, 60, 79, 70.0, 85.0)
    if s >= 40: return _lerp(s, 40, 59, 40.0, 60.0)
    return _lerp(s, 0, 39, 0.0, 30.0)


def _milestone_for_band(band: str) -> str:
    return {
        "LOW": "full_upfront",
        "MEDIUM": "balance_on_delivery_confirmation",
        "HIGH": "balance_after_quality_verification",
        "VERY_HIGH": "balance_after_full_delivery_and_quality_check",
    }.get(band, "balance_on_delivery_confirmation")


def _compute_supplier_risk_score(supplier_id: str) -> Dict[str, Any]:
    """
    Score 0..100 from current tables:

      • Delivery fulfillment ratio (qty_received / ordered)........ 35%
      • On-time delivery rate (GRN.receipt_date <= promised_date).. 25%
      • Quality OK rate (quality_ok)............................... 20%
      • Invoice rejection rate (APInvoices.status='REJECTED')...... 10% (penalty)
      • Payment failures (amount_paid=0 OR ref LIKE 'FAIL%')....... 10% (penalty)
    """
    ordered_q = """
    SELECT COALESCE(SUM(CAST(i.quantity AS FLOAT)), 0) AS ordered_qty
    FROM PurchaseOrderItems i
    JOIN PurchaseOrders p ON p.po_id = i.po_id
    WHERE p.supplier_id = %s
    """
    received_q = """
    SELECT COALESCE(SUM(CAST(g.qty_received AS FLOAT)), 0) AS received_qty
    FROM GoodsReceipts g
    JOIN PurchaseOrderItems i ON i.po_item_id = g.po_item_id
    JOIN PurchaseOrders p ON p.po_id = i.po_id
    WHERE p.supplier_id = %s
    """
    ontime_q = """
    SELECT
      COUNT(*) AS total_grn,
      SUM(CASE WHEN CAST(g.receipt_date AS DATE) <= CAST(i.promised_date AS DATE) THEN 1 ELSE 0 END) AS on_time
    FROM GoodsReceipts g
    JOIN PurchaseOrderItems i ON i.po_item_id = g.po_item_id
    JOIN PurchaseOrders p ON p.po_id = i.po_id
    WHERE p.supplier_id = %s
    """
    quality_q = """
    SELECT
      COUNT(*) AS total_grn,
      SUM(CASE WHEN quality_ok = 1 THEN 1 ELSE 0 END) AS ok_cnt
    FROM GoodsReceipts g
    JOIN PurchaseOrderItems i ON i.po_item_id = g.po_item_id
    JOIN PurchaseOrders p ON p.po_id = i.po_id
    WHERE p.supplier_id = %s
    """
    inv_q = """
    SELECT
      COUNT(*) AS total_inv,
      SUM(CASE WHEN UPPER(status)='REJECTED' THEN 1 ELSE 0 END) AS rej_cnt
    FROM APInvoices
    WHERE supplier_id = %s
    """
    pay_q = """
    SELECT
      COUNT(*) AS total_pay,
      SUM(CASE WHEN amount_paid = 0 OR UPPER(reference_no) LIKE 'FAIL%' THEN 1 ELSE 0 END) AS fail_cnt
    FROM Payments pa
    JOIN APInvoices ai ON ai.invoice_id = pa.invoice_id
    WHERE ai.supplier_id = %s
    """

    ordered_qty = _safe_float((_fetch_one(ordered_q, (supplier_id,)) or {}).get("ordered_qty"))
    received_qty = _safe_float((_fetch_one(received_q, (supplier_id,)) or {}).get("received_qty"))
    fulfillment = 1.0 if ordered_qty == 0 else _clamp(received_qty / max(ordered_qty, 1), 0.0, 1.0)

    ontime_row = _fetch_one(ontime_q, (supplier_id,)) or {}
    total_grn = int(ontime_row.get("total_grn") or 0)
    on_time = int(ontime_row.get("on_time") or 0)
    ontime_rate = 1.0 if total_grn == 0 else _clamp(on_time / max(total_grn, 1), 0.0, 1.0)

    quality_row = _fetch_one(quality_q, (supplier_id,)) or {}
    q_total = int(quality_row.get("total_grn") or 0)
    q_ok = int(quality_row.get("ok_cnt") or 0)
    quality_rate = 1.0 if q_total == 0 else _clamp(q_ok / max(q_total, 1), 0.0, 1.0)

    inv_row = _fetch_one(inv_q, (supplier_id,)) or {}
    inv_total = int(inv_row.get("total_inv") or 0)
    inv_rej = int(inv_row.get("rej_cnt") or 0)
    inv_rej_rate = 0.0 if inv_total == 0 else _clamp(inv_rej / max(inv_total, 1), 0.0, 1.0)

    pay_row = _fetch_one(pay_q, (supplier_id,)) or {}
    pay_total = int(pay_row.get("total_pay") or 0)
    pay_fail = int(pay_row.get("fail_cnt") or 0)
    pay_fail_rate = 0.0 if pay_total == 0 else _clamp(pay_fail / max(pay_total, 1), 0.0, 1.0)

    score = (
        35.0 * fulfillment +
        25.0 * ontime_rate +
        20.0 * quality_rate +
        10.0 * (1.0 - inv_rej_rate) +
        10.0 * (1.0 - pay_fail_rate)
    )

    return {
        "supplier_id": supplier_id,
        "risk_score": round(score, 2),
        "risk_band": _risk_band(score),
        "metrics": {
            "ordered_qty": ordered_qty,
            "received_qty": received_qty,
            "fulfillment_ratio": round(fulfillment, 3),
            "ontime_rate": round(ontime_rate, 3),
            "quality_ok_rate": round(quality_rate, 3),
            "invoice_rejection_rate": round(inv_rej_rate, 3),
            "payment_failure_rate": round(pay_fail_rate, 3),
        },
    }


def _recommend_payment_plan(po_id: int) -> Dict[str, Any]:
    base = _compute_base_po_amount(po_id)
    if base.get("error"):
        return base

    supplier_id = base["supplier_id"]
    risk = _compute_supplier_risk_score(supplier_id)
    score = risk["risk_score"]
    band = risk["risk_band"]

    upfront_pct = _upfront_percent(score)
    total = _safe_float(base["total_in_inr"])
    upfront_amt = round(total * upfront_pct / 100.0, 2)
    balance_amt = round(total - upfront_amt, 2)

    return {
        "po_id": po_id,
        "supplier_id": supplier_id,
        "currency": base["currency"],
        "exchange_rate": base["exchange_rate"],
        "totals": {
            "line_total": base["line_total"],
            "tax_amount": base["tax_amount"],
            "freight_amount": base["freight_amount"],
            "total_po_amount": base["total_po_amount"],
            "total_in_inr": total,
        },
        "risk": risk,
        "policy": {
            "band": band,
            "upfront_percent": round(upfront_pct, 2),
            "balance_percent": round(100.0 - upfront_pct, 2),
            "milestone": _milestone_for_band(band),
            "policy_version": "2025-08-21",
        },
        "amounts": {
            "upfront_amount": upfront_amt,
            "balance_amount": balance_amt,
        },
    }


# ---------- Tools ----------

@mcp.tool()
def calculate_base_payment(po_id: Union[int, str], supplier_id: str = None) -> dict:
    """Compute base PO total from items + tax + logistic_cost.

    Accepts either a DB po_id (1..N) or a request-style ref (PO-... / timestamp-ish) plus supplier_id,
    which will be mapped to static demo IDs: SUP001→1, SUP002→2, SUP003→3, SUP999→4.
    """
    try:
        # Try to normalize: int po_id passes through; request-style uses supplier mapping
        pid = _map_request_to_po(po_id, supplier_id)
        if not pid:
            return {
                "error": True,
                "message": (
                    f"Cannot resolve '{po_id}' to a DB po_id. "
                    "Pass po_id=1..4 or include supplier_id for static mapping."
                )
            }

        if not _po_exists(pid):
            return {"error": True, "message": f"PO {pid} not found in PurchaseOrders.po_id"}

        return _compute_base_po_amount(pid)
    except Exception as e:
        logger.exception("calculate_base_payment failed")
        return {"error": True, "message": f"calculate_base_payment failed: {e}"}


@mcp.tool()
def compute_supplier_risk(supplier_id: str) -> dict:
    """Compute supplier risk score 0..100 from historical performance."""
    try:
        sid = (supplier_id or "").strip()
        if not sid:
            return {"error": True, "message": "supplier_id is required"}
        return _compute_supplier_risk_score(sid)
    except Exception as e:
        logger.exception("compute_supplier_risk failed")
        return {"error": True, "message": f"compute_supplier_risk failed: {e}"}


@mcp.tool()
def recommend_payment_plan(po_id: Union[int, str], supplier_id: str = None) -> dict:
    """
    Payment plan policy by risk band:
      LOW (80–100): 100% upfront
      MED (60–79):  70–85% upfront, balance on delivery confirmation
      HIGH (40–59): 40–60% upfront, balance after quality verification
      VERY_HIGH(<40): 0–30% upfront, balance after full delivery + QC

    Accepts either a DB po_id (1..N) or a request-style ref with supplier_id,
    which will be mapped to static demo IDs: SUP001→1, SUP002→2, SUP003→3, SUP999→4.
    """
    try:
        # Surface missing env as a clean tool error, not a process crash
        missing = _missing_env()
        if missing:
            return {"error": True, "message": f"Missing required environment variables: {', '.join(missing)}"}

        # Normalize and validate
        pid = _map_request_to_po(po_id, supplier_id)
        if not pid:
            return {
                "error": True,
                "message": (
                    f"Cannot resolve '{po_id}' to a DB po_id. "
                    "Pass po_id=1..4 or include supplier_id for static mapping."
                )
            }

        if not _po_exists(pid):
            return {"error": True, "message": f"PO {pid} not found in PurchaseOrders.po_id"}

        return _recommend_payment_plan(pid)
    except Exception as e:
        logger.exception("recommend_payment_plan failed")
        return {"error": True, "message": f"recommend_payment_plan failed: {e}"}


@mcp.tool()
def recommend_payment_plan_by_supplier(supplier_id: str) -> dict:
    """
    Convenience tool for workflows that don't have the DB po_id handy.

    Strategy:
      - Uses the supplier's most recent PO (by created_at) to compute base totals.
      - Applies the same policy bands based on supplier risk.
    """
    try:
        missing = _missing_env()
        if missing:
            return {"error": True, "message": f"Missing required environment variables: {', '.join(missing)}"}

        sid = (supplier_id or "").strip()
        if not sid:
            return {"error": True, "message": "supplier_id is required"}

        # Pick the latest PO for this supplier (business rule: most recent is the active one)
        row = _fetch_one(
            """
            SELECT TOP 1 po_id
            FROM PurchaseOrders
            WHERE supplier_id = %s
            ORDER BY created_at DESC, po_id DESC
            """,
            (sid,)
        )
        if not row:
            return {"error": True, "message": f"No PurchaseOrders found for supplier_id='{sid}'"}

        pid = int(row["po_id"])
        return _recommend_payment_plan(pid)
    except Exception as e:
        logger.exception("recommend_payment_plan_by_supplier failed")
        return {"error": True, "message": f"recommend_payment_plan_by_supplier failed: {e}"}


@mcp.tool()
def explain_policy() -> dict:
    """Return current payment policy bands and milestones."""
    return {
        "policy_version": "2025-08-21",
        "bands": [
            {"band": "LOW", "score_range": "80–100", "upfront": "100%", "reason": "Excellent track record"},
            {"band": "MEDIUM", "score_range": "60–79", "upfront": "70–85%", "reason": "Good track record with minor concerns"},
            {"band": "HIGH", "score_range": "40–59", "upfront": "40–60%", "reason": "Performance issues detected"},
            {"band": "VERY_HIGH", "score_range": "<40", "upfront": "0–30%", "reason": "Significant reliability concerns"},
        ],
        "milestones": {
            "LOW": "full_upfront",
            "MEDIUM": "balance_on_delivery_confirmation",
            "HIGH": "balance_after_quality_verification",
            "VERY_HIGH": "balance_after_full_delivery_and_quality_check",
        },
    }

if __name__ == "__main__":
    asyncio.run(mcp.run(transport="stdio"))
