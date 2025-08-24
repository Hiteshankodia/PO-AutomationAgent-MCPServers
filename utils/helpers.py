"""Helper functions for the PO automation system."""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class DataManager:
    """Manages data loading and saving operations."""
    
    @staticmethod
    def load_json_data(file_path: str) -> Dict[str, Any]:
        """Load data from JSON file."""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"Data file not found: {file_path}")
                return {}
            
            with open(path, 'r') as file:
                return json.load(file)
        except Exception as e:
            logger.error(f"Error loading data from {file_path}: {e}")
            return {}
    
    @staticmethod
    def save_json_data(file_path: str, data: Dict[str, Any]) -> bool:
        """Save data to JSON file."""
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w') as file:
                json.dump(data, file, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"Error saving data to {file_path}: {e}")
            return False

def generate_po_id() -> str:
    """Generate a unique PO ID."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"PO-{timestamp}"

def format_currency(amount: float) -> str:
    """Format amount as currency."""
    return f"${amount:,.2f}"

def validate_po_request(po_request: Dict[str, Any]) -> tuple[bool, str]:
    """Validate PO request data."""
    required_fields = ["supplier_id", "amount", "department", "items"]
    
    for field in required_fields:
        if field not in po_request or not po_request[field]:
            return False, f"Missing required field: {field}"
    
    if not isinstance(po_request["amount"], (int, float)) or po_request["amount"] <= 0:
        return False, "Amount must be a positive number"
    
    if not isinstance(po_request["items"], list) or len(po_request["items"]) == 0:
        return False, "Items must be a non-empty list"
    
    return True, "Valid"
