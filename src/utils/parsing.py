"""
HTML parsing utilities for the Opportunity Hack Grant Finder.

This module provides functions for parsing and extracting information
from HTML content and other data sources.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# Configure logger
logger = logging.getLogger("parsing")

def extract_links(html: str, base_url: str, ignore_extensions: List[str] = None) -> List[str]:
    """
    Extract links from HTML content.
    
    Args:
        html: HTML content to parse
        base_url: Base URL for resolving relative links
        ignore_extensions: List of file extensions to ignore
        
    Returns:
        List[str]: List of absolute URLs
    """
    if ignore_extensions is None:
        ignore_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.css', '.js']
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            absolute_url = urljoin(base_url, href)
            
            # Skip URLs with ignored extensions
            if any(absolute_url.lower().endswith(ext) for ext in ignore_extensions):
                continue
                
            # Skip non-HTTP URLs
            parsed_url = urlparse(absolute_url)
            if parsed_url.scheme not in ('http', 'https'):
                continue
                
            # Skip fragment-only URLs (same page links)
            if parsed_url.netloc == urlparse(base_url).netloc and not parsed_url.path:
                continue
                
            links.append(absolute_url)
            
        return links
    
    except Exception as e:
        logger.error(f"Error extracting links from {base_url}: {str(e)}")
        return []

def extract_text_content(html: str, strip_scripts: bool = True) -> str:
    """
    Extract text content from HTML.
    
    Args:
        html: HTML content to parse
        strip_scripts: Whether to remove script tags before extracting text
        
    Returns:
        str: Extracted text content
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script tags if requested
        if strip_scripts:
            for script in soup.find_all('script'):
                script.decompose()
                
        # Get text with reasonable spacing
        text = soup.get_text(' ', strip=True)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text
    
    except Exception as e:
        logger.error(f"Error extracting text content: {str(e)}")
        return ""

def extract_metadata(html: str) -> Dict[str, str]:
    """
    Extract metadata from HTML content.
    
    Args:
        html: HTML content to parse
        
    Returns:
        Dict[str, str]: Dictionary of metadata
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        metadata = {}
        
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text(strip=True)
            
        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            metadata['description'] = meta_desc['content']
            
        # Extract OpenGraph metadata
        for meta in soup.find_all('meta', property=re.compile(r'^og:')):
            property_name = meta['property'][3:]  # Remove 'og:' prefix
            if 'content' in meta.attrs:
                metadata[f'og_{property_name}'] = meta['content']
                
        # Extract canonical URL
        canonical = soup.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            metadata['canonical_url'] = canonical['href']
            
        return metadata
    
    except Exception as e:
        logger.error(f"Error extracting metadata: {str(e)}")
        return {}

def extract_structured_data(html: str) -> List[Dict[str, Any]]:
    """
    Extract structured data (JSON-LD) from HTML content.
    
    Args:
        html: HTML content to parse
        
    Returns:
        List[Dict[str, Any]]: List of structured data objects
    """
    try:
        import json
        soup = BeautifulSoup(html, 'html.parser')
        structured_data = []
        
        # Find JSON-LD script tags
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                structured_data.append(data)
            except json.JSONDecodeError as e:
                logger.warning(f"Error parsing JSON-LD: {str(e)}")
                
        return structured_data
    
    except Exception as e:
        logger.error(f"Error extracting structured data: {str(e)}")
        return []

def extract_tables(html: str) -> List[List[List[str]]]:
    """
    Extract tables from HTML content.
    
    Args:
        html: HTML content to parse
        
    Returns:
        List[List[List[str]]]: List of tables, where each table is a list of rows, 
        and each row is a list of cell values
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        tables = []
        
        for table in soup.find_all('table'):
            parsed_table = []
            
            # Extract rows
            for tr in table.find_all('tr'):
                row = []
                
                # Extract cells (both th and td)
                for cell in tr.find_all(['th', 'td']):
                    # Get cell text, preserving some formatting
                    cell_content = cell.get_text(strip=True)
                    row.append(cell_content)
                    
                if row:  # Only add non-empty rows
                    parsed_table.append(row)
                    
            if parsed_table:  # Only add non-empty tables
                tables.append(parsed_table)
                
        return tables
    
    except Exception as e:
        logger.error(f"Error extracting tables: {str(e)}")
        return []

def parse_rss_feed(content: str) -> List[Dict[str, str]]:
    """
    Parse RSS feed content.
    
    Args:
        content: RSS feed content
        
    Returns:
        List[Dict[str, str]]: List of feed items
    """
    try:
        import feedparser
        
        feed = feedparser.parse(content)
        items = []
        
        for entry in feed.entries:
            item = {
                'title': entry.get('title', ''),
                'link': entry.get('link', ''),
                'published': entry.get('published', ''),
                'summary': entry.get('summary', '')
            }
            
            # Try to get the description if available
            if hasattr(entry, 'description'):
                item['description'] = entry.description
                
            # Get content if available
            if hasattr(entry, 'content'):
                item['content'] = entry.content[0].value if entry.content else ''
                
            items.append(item)
            
        return items
    
    except Exception as e:
        logger.error(f"Error parsing RSS feed: {str(e)}")
        return []