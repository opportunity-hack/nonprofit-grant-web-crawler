"""
Grant Writer Module for Opportunity Hack

This module uses Claude's API to automatically analyze grant opportunities
and draft grant applications for high-relevance grants.
"""

import os
import logging
import json
import re
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import aiohttp
import html2text

from src.config import (
    CLAUDE_API_CONFIG, 
    NONPROFIT_PROFILE, 
    RELEVANCE_CONFIG,
    OUTPUT_DIR
)

# Configure logger
logger = logging.getLogger("grant_writer")

class GrantWriter:
    """
    Uses Claude API to analyze grant pages and write grant applications
    for high-relevance opportunities.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the grant writer with Claude API credentials."""
        self.api_key = api_key or CLAUDE_API_CONFIG["api_key"]
        self.model = CLAUDE_API_CONFIG["model"]
        self.max_tokens = CLAUDE_API_CONFIG["max_tokens"]
        self.temperature = CLAUDE_API_CONFIG["temperature"]
        self.grants_written = 0
        self.max_grants = CLAUDE_API_CONFIG["max_grants_per_run"]
        self.output_dir = Path(CLAUDE_API_CONFIG["grant_output_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize HTML to text converter
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True
        self.html_converter.ignore_tables = False
        
    async def analyze_grant_page(self, url: str, html: str) -> Dict[str, Any]:
        """
        Analyzes a grant page using Claude to extract key information
        about the grant opportunity.
        """
        if not self.api_key:
            logger.warning("Claude API key not configured. Skipping grant analysis.")
            return {}
            
        # Convert HTML to text for better processing
        text_content = self.html_converter.handle(html)
        
        # Truncate if too long
        if len(text_content) > 12000:
            text_content = text_content[:12000] + "...[content truncated]"
            
        # Craft prompt for Claude to analyze the grant
        analysis_prompt = f"""
        You are a grant analysis expert. Examine the following grant webpage content and extract key information.
        
        Source URL: {url}
        
        WEBPAGE CONTENT:
        ```
        {text_content}
        ```
        
        Extract the following information about this grant opportunity in JSON format:
        1. Grant name/title
        2. Organization offering the grant
        3. Funding amount or range
        4. Application deadline
        5. Eligibility requirements
        6. Grant purpose/focus areas
        7. Application process
        8. Required documents
        9. Contact information
        10. Evaluation criteria
        
        For any fields where information is not available, use null.
        Format your response as a valid JSON object with these fields. Only return the JSON, no other explanatory text.
        """
        
        try:
            # Call Claude API for analysis
            response = await self._call_claude_api(analysis_prompt)
            
            # Extract JSON from response (Claude might include markdown formatting)
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response.strip()
                
            # Parse JSON response
            analysis_results = json.loads(json_str)
            
            # Add timestamp and source URL
            analysis_results["analysis_timestamp"] = datetime.now().isoformat()
            analysis_results["source_url"] = url
            
            return analysis_results
            
        except Exception as e:
            logger.error(f"Error analyzing grant page {url}: {str(e)}")
            return {"error": str(e), "source_url": url}
            
    async def write_grant_application(self, grant_analysis: Dict[str, Any]) -> Optional[str]:
        """
        Writes a grant application based on the grant analysis and nonprofit profile.
        """
        if not self.api_key or self.grants_written >= self.max_grants:
            logger.warning("Skipping grant writing (API key missing or max grants reached)")
            return None
            
        # Check if we have enough information to write a grant
        if not grant_analysis.get("grant_name") and not grant_analysis.get("title"):
            logger.warning("Insufficient grant information to write application")
            return None
            
        # Craft prompt for Claude to write the grant
        writing_prompt = f"""
        You are a professional grant writer with expertise in technology nonprofits. Write a compelling grant application for the following opportunity on behalf of our organization.
        
        GRANT OPPORTUNITY:
        {json.dumps(grant_analysis, indent=2)}
        
        OUR NONPROFIT ORGANIZATION:
        {json.dumps(NONPROFIT_PROFILE, indent=2)}
        
        Please write a complete grant application that:
        1. Follows any specific format requirements mentioned in the grant
        2. Includes a compelling narrative about our organization's work and impact
        3. Clearly explains how we will use the funding
        4. Aligns our mission and programs with the grant's purpose
        5. Provides concrete details about our organization, programs, and metrics
        6. Addresses all eligibility requirements and evaluation criteria
        7. Includes a strong conclusion
        
        Maintain a professional tone and focus on how Opportunity Hack's technology skills and volunteer engagement can create significant social impact. If the grant has specific sections or questions, organize your response accordingly.
        """
        
        try:
            # Call Claude API for grant writing
            application = await self._call_claude_api(writing_prompt)
            
            # Increment counter
            self.grants_written += 1
            
            # Save the grant application
            await self._save_grant_application(grant_analysis, application)
            
            return application
            
        except Exception as e:
            logger.error(f"Error writing grant application: {str(e)}")
            return None
    
    async def _call_claude_api(self, prompt: str) -> str:
        """
        Calls the Claude API with the given prompt.
        """
        if not self.api_key:
            raise ValueError("Claude API key not configured")
            
        headers = {
            "x-api-key": self.api_key,
            "content-type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["content"][0]["text"]
                else:
                    error_data = await response.text()
                    raise Exception(f"API error {response.status}: {error_data}")
    
    async def _save_grant_application(self, grant_analysis: Dict[str, Any], application: str) -> None:
        """
        Saves the generated grant application to a file.
        """
        try:
            # Create a file name based on the grant title and timestamp
            grant_name = grant_analysis.get("grant_name") or grant_analysis.get("title") or "unnamed_grant"
            grant_name = re.sub(r'[^\w\s-]', '', grant_name).strip().replace(' ', '_')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create the file path
            file_path = self.output_dir / f"{grant_name}_{timestamp}.md"
            
            # Create the content with metadata and the application
            content = f"""---
grant_title: {grant_analysis.get("grant_name") or grant_analysis.get("title") or "Unnamed Grant"}
organization: {grant_analysis.get("organization", "Unknown")}
funding_amount: {grant_analysis.get("funding_amount", "Not specified")}
deadline: {grant_analysis.get("deadline", "Not specified")}
source_url: {grant_analysis.get("source_url", "")}
generated_date: {datetime.now().isoformat()}
---

# Grant Application: {grant_analysis.get("grant_name") or grant_analysis.get("title") or "Unnamed Grant"}

{application}
"""
            
            # Write the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.info(f"Saved grant application to {file_path}")
            
        except Exception as e:
            logger.error(f"Error saving grant application: {str(e)}")
            
    async def should_write_grant(self, url: str, relevance_score: float) -> bool:
        """
        Determines if a grant opportunity is eligible for auto-writing.
        """
        # Check if API key is configured and feature is enabled
        if not self.api_key or not CLAUDE_API_CONFIG["enabled"] or not CLAUDE_API_CONFIG["auto_write_grants"]:
            return False
            
        # Check if we've reached the maximum number of grants for this run
        if self.grants_written >= self.max_grants:
            return False
            
        # Check relevance score threshold
        if relevance_score < RELEVANCE_CONFIG["auto_grant_threshold"]:
            return False
            
        return True