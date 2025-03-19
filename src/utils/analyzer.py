"""
Grant opportunity analyzer module for the Opportunity Hack Grant Finder.

This module provides intelligence for detecting and analyzing grant opportunities
from web content. It can extract key information like funding amounts, deadlines,
and calculates relevance scores.
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Set, Any, Tuple
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

from src.config import (
    OPPORTUNITY_HACK_KEYWORDS, TECH_SKILLS, NONPROFIT_SECTORS,
    GRANT_SIGNALS, RELEVANCE_CONFIG
)

# Configure logger
logger = logging.getLogger("analyzer")

class GrantDetector:
    """Detects and analyzes grant opportunities from web content."""
    
    @staticmethod
    def calculate_relevance_score(url: str, title: str, content: str) -> float:
        """
        Calculate relevance score based on various signals in the content.
        Returns a score between 0.0 and 1.0.
        """
        # Convert to lowercase for case-insensitive matching
        url_lower = url.lower()
        title_lower = title.lower()
        content_lower = content.lower()
        
        # Count keyword matches
        opportunity_keyword_matches = sum(
            keyword in content_lower for keyword in OPPORTUNITY_HACK_KEYWORDS
        )
        
        # Count grant signals
        grant_signal_matches = sum(
            signal in content_lower for signal in GRANT_SIGNALS
        )
        
        # Calculate base scores
        max_opportunity_keywords = len(OPPORTUNITY_HACK_KEYWORDS)
        max_grant_signals = len(GRANT_SIGNALS)
        
        # Weighted keyword score
        keyword_score = (
            opportunity_keyword_matches / max_opportunity_keywords
            if max_opportunity_keywords > 0 else 0
        ) * RELEVANCE_CONFIG["opportunity_keywords_weight"]
        
        # Weighted grant signals score
        signal_score = (
            grant_signal_matches / max_grant_signals
            if max_grant_signals > 0 else 0
        ) * RELEVANCE_CONFIG["grant_signals_weight"]
        
        # Base score is the average of the keyword and signal scores
        base_score = (keyword_score + signal_score) / (
            RELEVANCE_CONFIG["opportunity_keywords_weight"] + 
            RELEVANCE_CONFIG["grant_signals_weight"]
        )
        
        # Apply boosts
        boosts = 0.0
        
        # Boost if keywords in title (weighted more heavily)
        title_matches = sum(keyword in title_lower for keyword in OPPORTUNITY_HACK_KEYWORDS)
        if title_matches > 0:
            boosts += RELEVANCE_CONFIG["title_match_boost"]
        
        # Boost if keywords in URL
        url_matches = sum(keyword.replace(" ", "-") in url_lower for keyword in OPPORTUNITY_HACK_KEYWORDS)
        if url_matches > 0:
            boosts += RELEVANCE_CONFIG["url_match_boost"]
        
        # Boost if tech focus is found
        tech_matches = sum(tech in content_lower for tech in TECH_SKILLS)
        if tech_matches > 0:
            boosts += min(tech_matches * RELEVANCE_CONFIG["tech_match_boost"], 0.2)
        
        # Boost if funding amount is found
        if GrantDetector.extract_funding_amount(content) is not None:
            boosts += RELEVANCE_CONFIG["funding_match_boost"]
        
        # Boost if deadline is found
        if GrantDetector.extract_deadline(content) is not None:
            boosts += RELEVANCE_CONFIG["deadline_match_boost"]
        
        # Cap at 1.0
        return min(base_score + boosts, 1.0)
    
    @staticmethod
    def extract_title(html: str, url: str) -> str:
        """Extract title from HTML content."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try different title elements in order of preference
            title_elem = (
                soup.find('h1') or
                soup.find('meta', {'property': 'og:title'}) or
                soup.find('title')
            )
            
            if title_elem:
                title = title_elem.get_text().strip() if hasattr(title_elem, 'get_text') else title_elem.get('content', '')
                return title
            else:
                # If no title found, use domain name as fallback
                return f"Grant Opportunity at {urlparse(url).netloc}"
        except Exception as e:
            logger.error(f"Error extracting title from {url}: {str(e)}")
            return f"Grant Opportunity at {urlparse(url).netloc}"
    
    @staticmethod
    def extract_description(html: str) -> str:
        """Extract description from HTML content."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try different description elements
            desc_elem = (
                soup.find('meta', {'name': 'description'}) or
                soup.find('meta', {'property': 'og:description'})
            )
            
            if desc_elem and desc_elem.get('content'):
                return desc_elem.get('content', '')
            
            # Try to find the first paragraph
            first_p = soup.find('p')
            if first_p:
                return first_p.get_text().strip()
            
            # Use the first 500 chars of text content
            text = soup.get_text(' ', strip=True)
            return text[:500] + ('...' if len(text) > 500 else '')
        except Exception as e:
            logger.error(f"Error extracting description: {str(e)}")
            return ""
    
    @staticmethod
    def extract_funding_amount(text: str) -> Optional[Dict[str, Any]]:
        """Extract funding amount from text content."""
        # Patterns for different amount formats
        amount_patterns = [
            r'\$\s*([\d,]+(?:,\d{3})*(?:\.\d{1,2})?)(?:\s*-\s*\$\s*([\d,]+(?:,\d{3})*(?:\.\d{1,2})?))?',
            r'([\d,]+(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:USD|dollars)',
            r'grants?\s*of\s*(?:up to)?\s*\$\s*([\d,]+(?:,\d{3})*(?:\.\d{1,2})?)',
            r'awards?\s*(?:up to|of)\s*\$\s*([\d,]+(?:,\d{3})*(?:\.\d{1,2})?)',
            r'funding\s*(?:up to|of)\s*\$\s*([\d,]+(?:,\d{3})*(?:\.\d{1,2})?)',
            r'budget\s*(?:up to|of)\s*\$\s*([\d,]+(?:,\d{3})*(?:\.\d{1,2})?)'
        ]
        
        for pattern in amount_patterns:
            if match := re.search(pattern, text, re.IGNORECASE):
                try:
                    # Convert matched amount to float
                    amount_str = match.group(1).replace(',', '')
                    amount = float(amount_str)
                    
                    # Check for range
                    range_max = None
                    if len(match.groups()) > 1 and match.group(2):
                        range_max_str = match.group(2).replace(',', '')
                        range_max = float(range_max_str)
                    
                    return {
                        "amount": amount,
                        "currency": "USD",
                        "range_max": range_max
                    }
                except (ValueError, IndexError):
                    continue
        
        return None
    
    @staticmethod
    def extract_deadline(text: str) -> Optional[str]:
        """Extract application deadline from text content."""
        deadline_patterns = [
            r'(?:deadline|due date|closes|applications? due|submission deadline)(?:\s*:)?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(?:deadline|due date|closes|applications? due|submission deadline)(?:\s*:)?\s*(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4})',
            r'(?:deadline|due date|closes|applications? due|submission deadline)(?:\s*:)?\s*(\d{1,2}/\d{1,2}/\d{2,4})',
            r'(?:deadline|due date|closes|applications? due|submission deadline)(?:\s*:)?\s*(\d{4}-\d{2}-\d{2})',
            r'(?:applications? must be received by|submit before|apply before)(?:\s*:)?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(?:applications? must be received by|submit before|apply before)(?:\s*:)?\s*(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4})',
            r'(?:applications? must be received by|submit before|apply before)(?:\s*:)?\s*(\d{1,2}/\d{1,2}/\d{2,4})',
            r'(?:applications? must be received by|submit before|apply before)(?:\s*:)?\s*(\d{4}-\d{2}-\d{2})'
        ]
        
        for pattern in deadline_patterns:
            if match := re.search(pattern, text, re.IGNORECASE):
                return match.group(1).strip()
        
        return None
    
    @staticmethod
    def extract_application_url(html: str, base_url: str) -> Optional[str]:
        """Extract application URL from HTML content."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for links with relevant text
            application_keywords = [
                'apply', 'application', 'submit', 'proposal', 'register',
                'grant application', 'submit application', 'apply now',
                'submit proposal', 'application form'
            ]
            
            # Check for links with relevant text content
            for keyword in application_keywords:
                for link in soup.find_all('a', string=re.compile(keyword, re.IGNORECASE)):
                    return urljoin(base_url, link['href'])
            
            # Check for links with relevant text in href
            for keyword in application_keywords:
                for link in soup.find_all('a', href=re.compile(keyword, re.IGNORECASE)):
                    return urljoin(base_url, link['href'])
                    
            # Check for buttons with relevant text
            for keyword in application_keywords:
                button = soup.find('button', string=re.compile(keyword, re.IGNORECASE))
                if button and button.parent.name == 'a' and 'href' in button.parent.attrs:
                    return urljoin(base_url, button.parent['href'])
            
            return None
        except Exception as e:
            logger.error(f"Error extracting application URL: {str(e)}")
            return None
    
    @staticmethod
    def extract_tech_focus(text: str) -> List[str]:
        """Extract technology focus areas from text content."""
        text_lower = text.lower()
        return [skill for skill in TECH_SKILLS if skill in text_lower]
    
    @staticmethod
    def extract_nonprofit_sectors(text: str) -> List[str]:
        """Extract nonprofit sectors from text content."""
        text_lower = text.lower()
        return [sector for sector in NONPROFIT_SECTORS if sector in text_lower]
    
    @staticmethod
    def extract_eligibility(text: str) -> Optional[str]:
        """Extract eligibility requirements from text content."""
        eligibility_patterns = [
            r'(?:eligibility|who can apply|qualified candidates)(?:\s*:)?\s*([^.]*\.)',
            r'(?:eligible organizations|eligible applicants|eligibility criteria)(?:\s*:)?\s*([^.]*\.)',
            r'(?:requirements|qualifications)(?:\s*:)?\s*([^.]*\.)'
        ]
        
        for pattern in eligibility_patterns:
            if match := re.search(pattern, text, re.IGNORECASE):
                return match.group(1).strip()
        
        return None
    
    @staticmethod
    def check_volunteer_component(text: str) -> bool:
        """Check if the grant opportunity has a volunteer component."""
        volunteer_signals = [
            "volunteer", "pro bono", "skills-based volunteering",
            "technical volunteers", "volunteer developers", "volunteer time"
        ]
        
        text_lower = text.lower()
        return any(signal in text_lower for signal in volunteer_signals)
    
    @staticmethod
    def check_remote_participation(text: str) -> Optional[bool]:
        """Check if remote participation is mentioned."""
        remote_positive = [
            "remote participation", "virtual participation", "online participation",
            "participate remotely", "remote-friendly", "virtual event", 
            "online only", "remote work"
        ]
        
        remote_negative = [
            "in-person only", "on-site required", "no remote participation",
            "physical presence required", "must attend in person"
        ]
        
        text_lower = text.lower()
        
        if any(signal in text_lower for signal in remote_positive):
            return True
        if any(signal in text_lower for signal in remote_negative):
            return False
        
        return None
    
    @staticmethod
    def check_hackathon_eligible(text: str) -> bool:
        """Check if the grant is eligible for hackathon projects."""
        hackathon_negative = [
            "no prototypes", "established organizations only", 
            "minimum years of operation", "established revenue",
            "proof of financial stability", "minimum annual budget",
            "no startups", "existing projects only"
        ]
        
        hackathon_positive = [
            "prototype", "innovative", "new solutions", "early stage",
            "proof of concept", "pilot project", "hackathon", 
            "student projects", "startup", "early-stage", "idea stage"
        ]
        
        text_lower = text.lower()
        
        # If there are explicit negative signals, return False
        if any(signal in text_lower for signal in hackathon_negative):
            return False
            
        # If there are explicit positive signals, return True
        if any(signal in text_lower for signal in hackathon_positive):
            return True
            
        # Default to True (assume eligible unless proven otherwise)
        return True
    
    @classmethod
    def analyze_page(cls, url: str, html: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a page to determine if it contains a grant opportunity.
        If it does, extract and return grant details.
        """
        try:
            # Get plain text content for analysis
            soup = BeautifulSoup(html, 'html.parser')
            text_content = soup.get_text(' ', strip=True)
            
            # Extract title
            title = cls.extract_title(html, url)
            
            # Calculate relevance score
            relevance_score = cls.calculate_relevance_score(url, title, text_content)
            
            # Skip if not relevant enough
            if relevance_score < RELEVANCE_CONFIG["min_score"]:
                return None
            
            # Extract description
            description = cls.extract_description(html)
            
            # Extract other information
            funding_amount = cls.extract_funding_amount(text_content)
            deadline = cls.extract_deadline(text_content)
            application_url = cls.extract_application_url(html, url)
            eligibility = cls.extract_eligibility(text_content)
            
            # Opportunity Hack specific fields
            tech_focus = cls.extract_tech_focus(text_content)
            nonprofit_sectors = cls.extract_nonprofit_sectors(text_content)
            volunteer_component = cls.check_volunteer_component(text_content)
            remote_participation = cls.check_remote_participation(text_content)
            hackathon_eligible = cls.check_hackathon_eligible(text_content)
            
            # Create grant opportunity
            grant = {
                "title": title,
                "description": description,
                "source_url": url,
                "source_name": urlparse(url).netloc,
                "funding_amount": funding_amount,
                "deadline": deadline,
                "application_url": application_url,
                "eligibility": eligibility,
                "tech_focus": tech_focus,
                "nonprofit_sector": nonprofit_sectors,
                "volunteer_component": volunteer_component,
                "remote_participation": remote_participation,
                "hackathon_eligible": hackathon_eligible,
                "relevance_score": relevance_score,
                "found_date": datetime.now().isoformat()
            }
            
            return grant
            
        except Exception as e:
            logger.error(f"Error analyzing page {url}: {str(e)}")
            return None