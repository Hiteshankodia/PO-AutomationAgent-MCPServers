"""
Configuration package.

Re-exports
----------
azure_config : instance of AzureConfig
AzureConfig  : the class used to create that instance
"""

from .azure_config import azure_config, AzureConfig  # noqa: F401

__all__: list[str] = ["azure_config", "AzureConfig"]
