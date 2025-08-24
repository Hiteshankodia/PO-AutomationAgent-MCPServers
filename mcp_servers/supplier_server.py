import sys, pathlib
root = pathlib.Path(__file__).resolve().parents[1]  
if str(root) not in sys.path: sys.path.insert(0, str(root))

"""Supplier validation MCP server."""
import asyncio
import json
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from utils.helpers import DataManager

# Initialize MCP server
mcp = FastMCP("SupplierService")

# Load suppliers data
DATA_PATH = os.getenv("DATA_PATH", "data/suppliers.json")
SUPPLIERS = DataManager.load_json_data(DATA_PATH)

@mcp.tool()
def validate_supplier(supplier_id: str) -> dict:
    """Validate supplier and return supplier information."""
    supplier = SUPPLIERS.get(supplier_id)
    if not supplier:
        return {
            "valid": False, 
            "message": f"Supplier {supplier_id} not found",
            "supplier": None
        }
    
    if supplier["status"] != "approved":
        return {
            "valid": False, 
            "message": f"Supplier {supplier_id} is not approved (status: {supplier['status']})",
            "supplier": supplier
        }
    
    return {
        "valid": True,
        "supplier": supplier,
        "message": f"Supplier {supplier_id} validated successfully"
    }

@mcp.tool()
def check_supplier_capacity(supplier_id: str, order_value: float) -> dict:
    """Check if supplier can handle the order value."""
    supplier = SUPPLIERS.get(supplier_id)
    if not supplier:
        return {
            "capacity_ok": False, 
            "message": f"Supplier {supplier_id} not found",
            "max_capacity": 0,
            "requested": order_value
        }
    
    max_capacity = supplier.get("max_order_value", 0)
    
    return {
        "capacity_ok": order_value <= max_capacity,
        "max_capacity": max_capacity,
        "requested": order_value,
        "message": f"Capacity check: {order_value} vs {max_capacity}"
    }

@mcp.tool()
def get_supplier_details(supplier_id: str) -> dict:
    """Get detailed supplier information."""
    supplier = SUPPLIERS.get(supplier_id)
    if not supplier:
        return {
            "found": False,
            "message": f"Supplier {supplier_id} not found"
        }
    
    return {
        "found": True,
        "supplier": supplier,
        "message": "Supplier details retrieved"
    }

@mcp.tool()
def list_approved_suppliers(category: str = None) -> dict:
    """List all approved suppliers, optionally filtered by category."""
    approved_suppliers = {}
    
    for supplier_id, supplier_data in SUPPLIERS.items():
        if supplier_data["status"] == "approved":
            if category is None or category in supplier_data.get("categories", []):
                approved_suppliers[supplier_id] = {
                    "name": supplier_data["name"],
                    "rating": supplier_data["rating"],
                    "categories": supplier_data["categories"]
                }
    
    return {
        "count": len(approved_suppliers),
        "suppliers": approved_suppliers,
        "message": f"Found {len(approved_suppliers)} approved suppliers"
    }

if __name__ == "__main__":
    asyncio.run(mcp.run(transport="stdio"))
