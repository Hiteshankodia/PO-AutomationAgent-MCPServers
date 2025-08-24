import sys, pathlib
root = pathlib.Path(__file__).resolve().parents[1]  
if str(root) not in sys.path: sys.path.insert(0, str(root))

"""Budget validation MCP server."""
import asyncio
import os
from mcp.server.fastmcp import FastMCP
from utils.helpers import DataManager

# Initialize MCP server
mcp = FastMCP("BudgetService")

# Load budget data
DATA_PATH = os.getenv("DATA_PATH", "data/budgets.json")
BUDGETS = DataManager.load_json_data(DATA_PATH)

@mcp.tool()
def check_budget_availability(department_id: str, amount: float) -> dict:
    """Check if budget is available for the purchase."""
    budget = BUDGETS.get(department_id)
    if not budget:
        return {
            "available": False, 
            "message": f"Department {department_id} budget not found",
            "amount_requested": amount,
            "amount_available": 0,
            "budget_details": None
        }
    
    available = budget["allocated"] - budget["spent"] - budget["reserved"]
    
    return {
        "available": amount <= available,
        "amount_requested": amount,
        "amount_available": available,
        "budget_details": budget,
        "message": f"Budget check: requested ${amount:,.2f}, available ${available:,.2f}"
    }

@mcp.tool()
def reserve_budget(department_id: str, amount: float, po_id: str = None) -> dict:
    """Reserve budget for pending approval."""
    budget = BUDGETS.get(department_id)
    if not budget:
        return {
            "reserved": False, 
            "message": f"Department {department_id} not found",
            "po_id": po_id
        }
    
    available = budget["allocated"] - budget["spent"] - budget["reserved"]
    if amount > available:
        return {
            "reserved": False, 
            "message": f"Insufficient budget: requested ${amount:,.2f}, available ${available:,.2f}",
            "po_id": po_id
        }
    
    # Update budget reservation
    BUDGETS[department_id]["reserved"] += amount
    
    # Save updated budget data
    DataManager.save_json_data(DATA_PATH, BUDGETS)
    
    return {
        "reserved": True,
        "amount_reserved": amount,
        "new_reserved_total": BUDGETS[department_id]["reserved"],
        "po_id": po_id,
        "message": f"Successfully reserved ${amount:,.2f} for {po_id or 'PO'}"
    }

@mcp.tool()
def release_budget_reservation(department_id: str, amount: float, po_id: str = None) -> dict:
    """Release previously reserved budget."""
    budget = BUDGETS.get(department_id)
    if not budget:
        return {
            "released": False,
            "message": f"Department {department_id} not found",
            "po_id": po_id
        }
    
    if budget["reserved"] >= amount:
        BUDGETS[department_id]["reserved"] -= amount
        DataManager.save_json_data(DATA_PATH, BUDGETS)
        
        return {
            "released": True,
            "amount_released": amount,
            "new_reserved_total": BUDGETS[department_id]["reserved"],
            "po_id": po_id,
            "message": f"Successfully released ${amount:,.2f} reservation"
        }
    else:
        return {
            "released": False,
            "message": f"Cannot release ${amount:,.2f}: only ${budget['reserved']:,.2f} reserved",
            "po_id": po_id
        }

@mcp.tool()
def get_budget_summary(department_id: str) -> dict:
    """Get comprehensive budget summary for a department."""
    budget = BUDGETS.get(department_id)
    if not budget:
        return {
            "found": False,
            "message": f"Department {department_id} not found"
        }
    
    available = budget["allocated"] - budget["spent"] - budget["reserved"]
    utilization = (budget["spent"] / budget["allocated"]) * 100 if budget["allocated"] > 0 else 0
    
    return {
        "found": True,
        "department": budget["name"],
        "allocated": budget["allocated"],
        "spent": budget["spent"],
        "reserved": budget["reserved"],
        "available": available,
        "utilization_percent": round(utilization, 2),
        "fiscal_year": budget["fiscal_year"],
        "message": f"Budget summary for {budget['name']}"
    }

if __name__ == "__main__":
    asyncio.run(mcp.run(transport="stdio"))
