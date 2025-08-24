"""
Top-level package for the Purchase-Order Automation Agent.

Usage example
-------------
>>> from po_automation_agent import POAutomationApp
>>> app = POAutomationApp()
"""

from .main import POAutomationApp          # noqa: F401

__all__: list[str] = ["POAutomationApp"]