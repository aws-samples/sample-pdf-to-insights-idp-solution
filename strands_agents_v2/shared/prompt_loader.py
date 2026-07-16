"""
Prompt Loader Utility
Loads agent prompts from the assets/AgentPrompts.txt file
"""

import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class PromptLoader:
    """Loads and manages agent prompts from external file."""
    
    _prompts_cache: Optional[Dict[str, str]] = None
    
    @classmethod
    def load_prompts(cls) -> Dict[str, str]:
        """
        Load all prompts from assets/AgentPrompts.txt
        Returns a dictionary with agent names as keys and prompts as values
        """
        if cls._prompts_cache is not None:
            return cls._prompts_cache
        
        prompts = {}
        
        # Find the assets file - try multiple possible locations
        possible_paths = [
            '/app/assets/AgentPrompts.txt',  # Docker container path
            os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'AgentPrompts.txt'),  # Relative path
            'assets/AgentPrompts.txt'  # Direct path
        ]
        
        prompt_file_path = None
        for path in possible_paths:
            if os.path.exists(path):
                prompt_file_path = path
                break
        
        if not prompt_file_path:
            logger.warning("AgentPrompts.txt not found, using fallback prompts")
            return cls._get_fallback_prompts()
        
        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the content more carefully
            # Look for main section headers and their associated prompts
            
            # Find all prompt sections
            import re
            
            # Pattern to match prompt sections - looks for headers followed by triple quotes
            # Match either "## Something Prompt" or "## Something Agent" or "## Something Analyst"
            pattern = r'## ([\w\s]+)(?:\s+Prompt|\s+Agent|\s+Analyst)?\s*\n+"""(.*?)"""'
            matches = re.findall(pattern, content, re.DOTALL)
            
            for header, prompt_content in matches:
                header = header.strip()
                prompt = prompt_content.strip()
                
                # Determine the agent type from header
                agent_type = None
                if 'Coordinator' in header:
                    agent_type = 'coordinator'
                elif 'MarketAnalyst' in header or 'Market Analyst' in header:
                    agent_type = 'market_analyst'
                elif 'Investment' in header:
                    agent_type = 'investment_advisory'
                elif 'External' in header:
                    agent_type = 'external_api'
                
                if agent_type and prompt:
                    prompts[agent_type] = prompt
                    logger.info(f"Loaded prompt for {agent_type} from file")
            
            cls._prompts_cache = prompts
            return prompts
            
        except Exception as e:
            logger.error(f"Error loading prompts from file: {e}")
            return cls._get_fallback_prompts()
    
    @classmethod
    def get_prompt(cls, agent_type: str) -> str:
        """
        Get prompt for a specific agent type
        
        Args:
            agent_type: One of 'coordinator', 'market_analyst', 'investment_advisory', 'external_api'
            
        Returns:
            The prompt string for the agent
        """
        prompts = cls.load_prompts()
        
        if agent_type in prompts:
            logger.info(f"Using prompt from AgentPrompts.txt for {agent_type}")
            return prompts[agent_type]
        else:
            logger.warning(f"No prompt found for {agent_type}, using fallback")
            return cls._get_fallback_prompt(agent_type)
    
    @classmethod
    def _get_fallback_prompts(cls) -> Dict[str, str]:
        """Return minimal fallback prompts if file cannot be loaded."""
        return {
            'coordinator': "You are the BDA Coordinator Agent, orchestrating specialist agents for real estate analysis.",
            'market_analyst': "You are the BDA Market Analyst Agent, specializing in financial calculations and market trends.",
            'investment_advisory': "You are the BDA Investment Advisory Agent, providing portfolio recommendations and risk assessment.",
            'external_api': "You are the BDA External API Agent, retrieving real-time market data and external information."
        }
    
    @classmethod
    def _get_fallback_prompt(cls, agent_type: str) -> str:
        """Get a single fallback prompt."""
        fallback_prompts = cls._get_fallback_prompts()
        return fallback_prompts.get(
            agent_type, 
            f"You are the BDA {agent_type.replace('_', ' ').title()} Agent."
        )