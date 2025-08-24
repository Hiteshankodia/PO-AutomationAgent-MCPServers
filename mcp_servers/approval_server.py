import sys, pathlib
root = pathlib.Path(__file__).resolve().parents[1]  
if str(root) not in sys.path: sys.path.insert(0, str(root))

"""Approval matrix MCP server."""
import asyncio
import os
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from utils.helpers import DataManager

# Initialize MCP server
mcp = FastMCP("ApprovalService")

# Load approval matrix data
DATA_PATH = os.getenv("DATA_PATH", "data/approval_matrix.json")
APPROVAL_DATA = DataManager.load_json_data(DATA_PATH)

@mcp.tool()
def get_required_approvers(amount: float, department: str = None) -> dict:
    """Get list of required approvers based on amount and department."""
    thresholds = APPROVAL_DATA.get("thresholds", [])
    
    for threshold in thresholds:
        if amount <= threshold["max_amount"]:
            return {
                "approvers_required": threshold["required_approvers"],
                "approval_needed": not threshold.get("auto_approve", False),
                "threshold": threshold["max_amount"],
                "auto_approve": threshold.get("auto_approve", False),
                "amount": amount,
                "message": f"Approval requirements determined for ${amount:,.2f}"
            }
    
    # Fallback to highest threshold
    highest_threshold = thresholds[-1] if thresholds else {}
    return {
        "approvers_required": highest_threshold.get("required_approvers", ["director"]),
        "approval_needed": True,
        "threshold": highest_threshold.get("max_amount", float('inf')),
        "auto_approve": False,
        "amount": amount,
        "message": f"Using highest threshold for ${amount:,.2f}"
    }

@mcp.tool()
def send_approval_request(po_id: str, approvers: list, po_details: dict) -> dict:
    """Send approval request to required approvers."""
    approver_details = APPROVAL_DATA.get("approvers", {})
    
    notifications_sent = []
    for approver_role in approvers:
        approver_info = approver_details.get(approver_role, {})
        notifications_sent.append({
            "role": approver_role,
            "name": approver_info.get("name", f"Unknown {approver_role}"),
            "email": approver_info.get("email", f"{approver_role}@company.com"),
            "sent_at": datetime.now().isoformat()
        })
    
    return {
        "requests_sent": len(approvers),
        "approvers": notifications_sent,
        "po_id": po_id,
        "estimated_response_time": "24-48 hours",
        "po_amount": po_details.get("amount", 0),
        "message": f"Approval requests sent to {len(approvers)} approvers for {po_id}"
    }

@mcp.tool()
def check_approval_status(po_id: str) -> dict:
    """Check the current approval status of a PO (simulated)."""
    # In a real implementation, this would check a database
    # For now, we'll simulate based on PO creation time
    return {
        "po_id": po_id,
        "status": "pending",
        "approvals_received": 0,
        "approvals_required": 2,
        "last_updated": datetime.now().isoformat(),
        "message": f"Approval status for {po_id}: pending"
    }

@mcp.tool()
def get_approval_matrix() -> dict:
    """Get the complete approval matrix configuration."""
    return {
        "matrix": APPROVAL_DATA,
        "message": "Approval matrix configuration retrieved"
    }

@mcp.tool()
def simulate_approval(po_id: str, approver_role: str, decision: str) -> dict:
    """Simulate an approval decision (for testing purposes)."""
    if decision.lower() not in ["approved", "rejected"]:
        return {
            "valid": False,
            "message": "Decision must be 'approved' or 'rejected'"
        }
    
    approver_info = APPROVAL_DATA.get("approvers", {}).get(approver_role, {})
    
    return {
        "valid": True,
        "po_id": po_id,
        "approver": {
            "role": approver_role,
            "name": approver_info.get("name", f"Unknown {approver_role}"),
            "email": approver_info.get("email", f"{approver_role}@company.com")
        },
        "decision": decision.lower(),
        "timestamp": datetime.now().isoformat(),
        "message": f"Approval {decision.lower()} by {approver_role} for {po_id}"
    }

if __name__ == "__main__":
    asyncio.run(mcp.run(transport="stdio"))
