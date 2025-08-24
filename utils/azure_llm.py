"""Azure OpenAI integration utilities."""
from typing import Optional
from langchain_openai import AzureChatOpenAI
from langchain_core.language_models import BaseChatModel
from config.azure_config import azure_config
import logging

logger = logging.getLogger(__name__)

class AzureLLMManager:
    """Manager for Azure OpenAI LLM instances."""
    
    def __init__(self):
        self._llm: Optional[BaseChatModel] = None
        self._initialize_llm()
    
    def _initialize_llm(self) -> None:
        """Initialize Azure OpenAI LLM."""
        try:
            if not azure_config.is_configured:
                raise ValueError("Azure OpenAI configuration is incomplete")
            
            self._llm = AzureChatOpenAI(
                azure_endpoint=azure_config.endpoint,
                azure_deployment=azure_config.deployment_name,
                api_version=azure_config.api_version,
                api_key=azure_config.api_key,
                model=azure_config.model_name,
                temperature=0.1,
                max_tokens=1000
            )
            logger.info("Azure OpenAI LLM initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI LLM: {e}")
            raise
    
    @property
    def llm(self) -> BaseChatModel:
        """Get the LLM instance."""
        if self._llm is None:
            self._initialize_llm()
        return self._llm
    
    def get_llm_with_tools(self, tools: list) -> BaseChatModel:
        """Get LLM instance bound with tools."""
        return self.llm.bind_tools(tools)

# Global LLM manager instance
llm_manager = AzureLLMManager()