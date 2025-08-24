
"""State definitions for PO workflow."""
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class POWorkflowState(TypedDict, total=False):
    """State structure for PO workflow."""

    # LangGraph message accumulator
    messages: Annotated[List[BaseMessage], add_messages]

    # Core request and identifiers
    po_request: Dict[str, Any]
    po_id: str

    # Stage results
    supplier_validation: Dict[str, Any]
    budget_check: Dict[str, Any]
    approval_status: Dict[str, Any]

    # Payment calculation
    payment_plan: Dict[str, Any]          # NEW: ensure plan survives between nodes
    payment_attempted: bool               # already used to avoid loops

    # Notifications & decision
    notifications: List[Dict[str, Any]]
    final_decision: str
    decision_reason: str

    # Bookkeeping
    processing_time: float
    errors: List[str]
