import sys, pathlib
root = pathlib.Path(__file__).resolve().parents[1]  
if str(root) not in sys.path: sys.path.insert(0, str(root))

"""Notification MCP server for sending alerts and updates."""
import asyncio
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("NotificationService")

@mcp.tool()
def send_email_notification(recipient: str, subject: str, body: str, po_id: str = None) -> dict:
    """Send email notification (simulated)."""
    # In a real implementation, this would integrate with email service
    notification_id = f"EMAIL_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    return {
        "sent": True,
        "notification_id": notification_id,
        "recipient": recipient,
        "subject": subject,
        "po_id": po_id,
        "sent_at": datetime.now().isoformat(),
        "method": "email",
        "message": f"Email notification sent to {recipient}"
    }

@mcp.tool()
def send_slack_notification(channel: str, message: str, po_id: str = None) -> dict:
    """Send Slack notification (simulated)."""
    notification_id = f"SLACK_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    return {
        "sent": True,
        "notification_id": notification_id,
        "channel": channel,
        "message": message,
        "po_id": po_id,
        "sent_at": datetime.now().isoformat(),
        "method": "slack",
        "message": f"Slack notification sent to {channel}"
    }

@mcp.tool()
def notify_po_status_change(po_id: str, old_status: str, new_status: str, stakeholders: list) -> dict:
    """Notify stakeholders of PO status changes."""
    notifications = []
    
    for stakeholder in stakeholders:
        notification = {
            "recipient": stakeholder,
            "message": f"PO {po_id} status changed from {old_status} to {new_status}",
            "timestamp": datetime.now().isoformat()
        }
        notifications.append(notification)
    
    return {
        "notifications_sent": len(notifications),
        "notifications": notifications,
        "po_id": po_id,
        "status_change": f"{old_status} -> {new_status}",
        "message": f"Status change notifications sent for {po_id}"
    }

@mcp.tool()
def send_approval_reminder(po_id: str, approver_email: str, days_pending: int) -> dict:
    """Send approval reminder notification."""
    return {
        "sent": True,
        "po_id": po_id,
        "approver": approver_email,
        "days_pending": days_pending,
        "reminder_type": "approval_pending",
        "sent_at": datetime.now().isoformat(),
        "message": f"Approval reminder sent for {po_id} (pending {days_pending} days)"
    }

if __name__ == "__main__":
    asyncio.run(mcp.run(transport="stdio"))
