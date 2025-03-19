"""
Opportunity Hack Grant Finder

A specialized crawler to identify grants and funding opportunities
relevant to Opportunity Hack's mission of technology for social good.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import urlparse

import feedparser
from googleapiclient.discovery import build
from pydantic import BaseModel, Field, validator
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
import pandas as pd
from dotenv import load_dotenv
import sys

from src.config import (
    TARGET_URLS, SEARCH_QUERIES, RSS_FEEDS, 
    LOG_DIR, OUTPUT_DIR, CACHE_DIR, GOOGLE_API_KEY, GOOGLE_CSE_ID,
    CRAWLER_CONFIG, RELEVANCE_CONFIG, EMAIL_CONFIG, VISUAL_CONFIG, GOOGLE_API_CONFIG
)
from src.utils.crawler import AdvancedCrawler
from src.utils.analyzer import GrantDetector

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RichHandler(rich_tracebacks=True),
        logging.FileHandler(LOG_DIR / f"opportunity_hack_crawler_{datetime.now():%Y%m%d}.log")
    ]
)
logger = logging.getLogger("opportunity_hack_grant_finder")

# Data Models
class FundingAmount(BaseModel):
    """Model for funding amount information."""
    amount: float
    currency: str = "USD"
    range_max: Optional[float] = None
    
    def __str__(self) -> str:
        if self.range_max:
            return f"{self.currency} {self.amount:,.2f} - {self.range_max:,.2f}"
        return f"{self.currency} {self.amount:,.2f}"

class OpportunityHackGrant(BaseModel):
    """Data model for grants relevant to Opportunity Hack."""
    title: str
    description: str
    source_url: str
    source_name: str
    funding_amount: Optional[FundingAmount] = None
    deadline: Optional[str] = None
    application_url: Optional[str] = None
    eligibility: Optional[str] = None
    
    # Opportunity Hack specific fields
    tech_focus: List[str] = Field(default_factory=list)
    skill_requirements: List[str] = Field(default_factory=list)
    nonprofit_sector: List[str] = Field(default_factory=list)
    volunteer_component: bool = False
    hackathon_eligible: bool = True
    remote_participation: Optional[bool] = None
    
    # Metadata
    relevance_score: float = 0.0
    found_date: datetime = Field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert grant to dictionary."""
        data = self.model_dump()
        # Convert datetime to string
        data["found_date"] = self.found_date.isoformat()
        return data
    
    @validator("relevance_score")
    def validate_relevance_score(cls, v):
        """Validate relevance score is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError("Relevance score must be between 0 and 1")
        return v

class OpportunityHackGrantFinder:
    """
    Specialized grant finder for Opportunity Hack that combines
    direct URL crawling with internet search capabilities.
    """
    
    def __init__(
        self,
        max_concurrent_requests: int = CRAWLER_CONFIG["max_concurrent_requests"],
        rate_limit_delay: float = CRAWLER_CONFIG["rate_limit_delay"],
        max_depth: int = CRAWLER_CONFIG["max_depth"],
        proxy_list: Optional[List[str]] = None,
        use_google_search: bool = CRAWLER_CONFIG["use_google_search"],
        use_rss_feeds: bool = CRAWLER_CONFIG["use_rss_feeds"],
        incremental_save: bool = CRAWLER_CONFIG["incremental_save"],
        save_interval: int = CRAWLER_CONFIG["save_interval"],
        output_dir: Path = OUTPUT_DIR,
    ):
        """Initialize the grant finder."""
        self.max_concurrent_requests = max_concurrent_requests
        self.rate_limit_delay = rate_limit_delay
        self.max_depth = max_depth
        self.proxy_list = proxy_list or []
        self.use_google_search = use_google_search
        self.use_rss_feeds = use_rss_feeds
        self.incremental_save = incremental_save
        self.save_interval = save_interval
        self.output_dir = output_dir
        
        # Rich console for visual output
        self.console = Console()
        
        # Initialize the advanced crawler
        self.crawler = AdvancedCrawler(
            max_concurrent_requests=max_concurrent_requests,
            max_depth=max_depth,
            rich_console=self.console if VISUAL_CONFIG["use_rich_display"] else None
        )
        
        # Internal state
        self.grants_found: List[OpportunityHackGrant] = []
        self.grants_saved_count = 0
        self.new_grants_since_save = 0
        
        # Initialize file paths for incremental saving
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.json_path = self.output_dir / f"opportunity_hack_grants_{self.timestamp}.json"
        self.csv_path = self.output_dir / f"opportunity_hack_grants_{self.timestamp}.csv"
        
        # Initialize files for incremental saving if needed
        if self.incremental_save:
            self._initialize_output_files()
        
        # URLs to crawl
        self.direct_urls = TARGET_URLS
        self.search_queries = SEARCH_QUERIES
        self.rss_feeds = RSS_FEEDS
        
    def _initialize_output_files(self) -> None:
        """Initialize the output files for incremental saving."""
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize JSON file with an empty array
        with open(self.json_path, 'w', encoding='utf-8') as f:
            f.write('[\n')  # Open JSON array
            
        # Initialize CSV file with header
        # We'll create a temporary grant to extract the headers
        temp_grant = OpportunityHackGrant(
            title="", 
            description="", 
            source_url="", 
            source_name=""
        )
        df = pd.DataFrame([self._prepare_csv_data(temp_grant)])
        # Write only the header row
        df.to_csv(self.csv_path, index=False)
    
    def _prepare_csv_data(self, grant: OpportunityHackGrant) -> Dict[str, Any]:
        """Prepare grant data for CSV format."""
        data = grant.to_dict()
        
        # Flatten nested structures
        if grant.funding_amount:
            data['amount'] = grant.funding_amount.amount
            data['currency'] = grant.funding_amount.currency
            data['range_max'] = grant.funding_amount.range_max
            del data['funding_amount']
        
        # Convert lists to strings
        data['tech_focus'] = ', '.join(data['tech_focus'])
        data['skill_requirements'] = ', '.join(data['skill_requirements'])
        data['nonprofit_sector'] = ', '.join(data['nonprofit_sector'])
        
        return data
        
    async def save_grant_incrementally(self, grant: OpportunityHackGrant) -> None:
        """Save a single grant incrementally to both JSON and CSV files."""
        if not self.incremental_save or not grant:
            return
            
        try:
            # Append to JSON (with proper comma handling)
            with open(self.json_path, 'a', encoding='utf-8') as f:
                # Add comma if not the first item
                prefix = "" if self.grants_saved_count == 0 else ",\n"
                json_str = json.dumps(grant.to_dict(), indent=2, ensure_ascii=False)
                f.write(f"{prefix}{json_str}")
            
            # Append to CSV
            csv_data = self._prepare_csv_data(grant)
            df = pd.DataFrame([csv_data])
            # Use mode='a' and header=False to append without header
            df.to_csv(self.csv_path, mode='a', header=False, index=False)
            
            # Update counters
            self.grants_saved_count += 1
            self.new_grants_since_save = 0
            
            logger.debug(f"Incrementally saved grant: {grant.title} ({self.grants_saved_count} total)")
        except Exception as e:
            logger.error(f"Error saving grant incrementally: {str(e)}")
    
    async def process_page(self, url: str, html: str, depth: int) -> Optional[OpportunityHackGrant]:
        """Process a page to extract grant information using the analyzer."""
        # Use the GrantDetector to analyze the page
        grant_data = GrantDetector.analyze_page(url, html)
        
        if not grant_data:
            return None
            
        # Convert funding amount to FundingAmount model if present
        funding_amount = None
        if grant_data.get('funding_amount'):
            funding_data = grant_data['funding_amount']
            funding_amount = FundingAmount(
                amount=funding_data['amount'],
                currency=funding_data.get('currency', 'USD'),
                range_max=funding_data.get('range_max')
            )
        
        # Check if funding amount is under $100 - if so, set it to None
        if funding_amount and funding_amount.amount < 100:
            funding_amount = None
            logger.debug(f"Ignoring funding amount below $100 for {url}")
            # Skip it
            return None
            
        # Create grant opportunity using our data model
        try:
            grant = OpportunityHackGrant(
                title=grant_data['title'],
                description=grant_data['description'],
                source_url=grant_data['source_url'],
                source_name=grant_data['source_name'],
                funding_amount=funding_amount,
                deadline=grant_data.get('deadline'),
                application_url=grant_data.get('application_url'),
                eligibility=grant_data.get('eligibility'),
                tech_focus=grant_data.get('tech_focus', []),
                nonprofit_sector=grant_data.get('nonprofit_sector', []),
                volunteer_component=grant_data.get('volunteer_component', False),
                hackathon_eligible=grant_data.get('hackathon_eligible', True),
                remote_participation=grant_data.get('remote_participation'),
                relevance_score=grant_data['relevance_score'],
                found_date=datetime.fromisoformat(grant_data['found_date'])
            )
            
            logger.info(f"Found grant opportunity: {grant.title} at {url} (score: {grant.relevance_score:.2f})")
            
            # Check if this is a high-relevance grant that should be auto-processed with Claude
            if grant.relevance_score >= RELEVANCE_CONFIG["auto_grant_threshold"]:
                await self._process_high_relevance_grant(url, html, grant.relevance_score)
            
            # Add to memory list
            self.grants_found.append(grant)
            
            # Track grants found since last save
            self.new_grants_since_save += 1
            
            # Check if we should save incrementally
            if self.incremental_save and self.save_interval > 0 and self.new_grants_since_save >= self.save_interval:
                await self.save_grant_incrementally(grant)
            
            return grant
            
        except Exception as e:
            logger.error(f"Error creating grant model from {url}: {str(e)}")
            return None
    
    async def _process_high_relevance_grant(self, url: str, html: str, relevance_score: float) -> None:
        """
        Process high-relevance grants with Claude API for automated grant writing.
        """
        # Import here to avoid circular imports
        from src.utils.grant_writer import GrantWriter
        
        try:
            # Initialize grant writer if not already done
            if not hasattr(self, 'grant_writer'):
                self.grant_writer = GrantWriter()
            
            # Check if we should analyze and write a grant for this opportunity
            if await self.grant_writer.should_write_grant(url, relevance_score):
                logger.info(f"High relevance grant detected ({relevance_score:.2f}). Analyzing with Claude API: {url}")
                
                # Analyze the grant page
                grant_analysis = await self.grant_writer.analyze_grant_page(url, html)
                
                if grant_analysis and not grant_analysis.get('error'):
                    # Write a grant application
                    application = await self.grant_writer.write_grant_application(grant_analysis)
                    
                    if application:
                        logger.info(f"Successfully wrote grant application for {url}")
                    else:
                        logger.warning(f"Failed to write grant application for {url}")
                else:
                    logger.warning(f"Failed to analyze grant page: {url}")
        
        except Exception as e:
            logger.error(f"Error in high relevance grant processing for {url}: {str(e)}")
    
    async def search_with_google(self) -> List[str]:
        """Search for grants using Google Custom Search API with cost controls."""
        # Check for missing or invalid API credentials
        if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
            logger.warning("Google API credentials not provided. Skipping Google search.")
            return []
            
        # Check if the API_KEY or CSE_ID might be invalid
        if len(GOOGLE_API_KEY) < 20 or len(GOOGLE_CSE_ID) < 10:
            logger.warning("Google API credentials appear to be invalid. Skipping Google search.")
            return []
        
        try:
            # Check if we should use cached results
            if GOOGLE_API_CONFIG["use_google_cache"]:
                cache_path = Path(CACHE_DIR) / "google_search_cache.json"
                if cache_path.exists():
                    logger.info("Checking for cached Google search results...")
                    try:
                        # Load cached results
                        with open(cache_path, 'r') as f:
                            import json
                            cache_data = json.load(f)
                            logger.info(f"Loaded {len(cache_data.get('urls', []))} cached Google search results")
                            
                        # Check cache expiry
                        from datetime import datetime, timedelta
                        cache_time = datetime.fromisoformat(cache_data.get('timestamp', '2020-01-01T00:00:00'))
                        cache_expiry = timedelta(seconds=GOOGLE_API_CONFIG["google_cache_expiry"])
                        
                        if datetime.now() - cache_time < cache_expiry or GOOGLE_API_CONFIG["use_google_cache"]:
                            logger.info(f"Using cached Google search results from {cache_time.isoformat()}")
                            return cache_data.get('urls', [])
                    except Exception as e:
                        logger.warning(f"Error reading Google search cache: {str(e)}")
            
            # Initialize Google API client
            service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
            
            # Limit number of queries for cost control
            max_queries = min(len(self.search_queries), GOOGLE_API_CONFIG["max_queries_per_run"])
            queries_to_use = self.search_queries[:max_queries]
            
            logger.info(f"Running {max_queries} Google searches (limited by cost controls)")
            
            all_urls = []
            for query in queries_to_use:
                try:
                    # Execute search with limited results
                    max_results = GOOGLE_API_CONFIG["max_results_per_query"]
                    try:
                        # For advanced searches, remove special operators that might cause issues
                        cleaned_query = query
                        if 'filetype:' in query:
                            cleaned_query = query.split('filetype:')[0].strip()
                            logger.info(f"Removed filetype operator from query: {query} -> {cleaned_query}")
                            
                        if 'AND' in query or 'OR' in query:
                            cleaned_query = query.replace('AND', '').replace('OR', '').replace('"', '')
                            logger.info(f"Removed boolean operators from query: {query} -> {cleaned_query}")
                            
                        # Make the request with the cleaned query
                        # Google Custom Search API has a maximum limit of 10 results per query
                        max_results = min(max_results, 10)  # Ensure we don't exceed API limit
                        res = service.cse().list(q=cleaned_query, cx=GOOGLE_CSE_ID, num=max_results).execute()
                        
                        # Extract URLs
                        if 'items' in res:
                            urls = [item['link'] for item in res['items']]
                            all_urls.extend(urls)
                            logger.info(f"Found {len(urls)} results for query: {cleaned_query}")
                        else:
                            logger.warning(f"No results found for query: {cleaned_query}")
                    except Exception as e:
                        logger.error(f"Error executing search for '{query}': {str(e)}")
                        
                    # Rate limiting
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error searching with query '{query}': {str(e)}")
                    continue
            
            # Store results in cache
            unique_urls = list(set(all_urls))
            logger.info(f"Found {len(unique_urls)} unique URLs from Google search")
            if GOOGLE_API_CONFIG["use_google_cache"]:
                try:
                    cache_data = {
                        'timestamp': datetime.now().isoformat(),
                        'urls': unique_urls
                    }
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(cache_path, 'w') as f:
                        import json
                        json.dump(cache_data, f)
                    logger.info(f"Cached {len(unique_urls)} Google search results")
                except Exception as e:
                    logger.warning(f"Error writing Google search cache: {str(e)}")
            
            # Track API usage if enabled
            if GOOGLE_API_CONFIG["enable_budget_tracking"]:
                try:
                    # Simple cost model: $5 per 1000 queries, each query returns max_results results
                    cost_per_query = 5.0 / 1000.0
                    total_cost = len(queries_to_use) * cost_per_query
                    
                    # Load or initialize usage tracking
                    usage_file = Path(GOOGLE_API_CONFIG["budget_tracking_file"])
                    if usage_file.exists():
                        with open(usage_file, 'r') as f:
                            usage_data = json.load(f)
                    else:
                        usage_data = {
                            'current_month': datetime.now().strftime('%Y-%m'),
                            'monthly_usage': 0.0,
                            'total_usage': 0.0,
                            'usage_history': []
                        }
                    
                    # Update usage data
                    current_month = datetime.now().strftime('%Y-%m')
                    if current_month != usage_data['current_month']:
                        # New month, reset counter
                        usage_data['usage_history'].append({
                            'month': usage_data['current_month'],
                            'cost': usage_data['monthly_usage']
                        })
                        usage_data['current_month'] = current_month
                        usage_data['monthly_usage'] = total_cost
                    else:
                        # Same month, add to counter
                        usage_data['monthly_usage'] += total_cost
                    
                    usage_data['total_usage'] += total_cost
                    
                    # Save updated usage data
                    usage_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(usage_file, 'w') as f:
                        json.dump(usage_data, f, indent=2)
                    
                    logger.info(f"Google API usage: ${total_cost:.4f} (Monthly: ${usage_data['monthly_usage']:.2f})")
                except Exception as e:
                    logger.warning(f"Error tracking Google API usage: {str(e)}")
            
            return unique_urls
            
        except Exception as e:
            logger.error(f"Error setting up Google search: {str(e)}")
            return []
    
    async def fetch_rss_feeds(self) -> List[str]:
        """Fetch and parse RSS feeds for grant opportunities."""
        if not self.use_rss_feeds:
            return []
        
        all_urls = []
        for feed_url in self.rss_feeds:
            try:
                # Parse feed
                feed = feedparser.parse(feed_url)
                
                # Extract URLs
                for entry in feed.entries:
                    if hasattr(entry, 'link'):
                        all_urls.append(entry.link)
                
                logger.info(f"Fetched {len(feed.entries)} entries from {feed_url}")
                
            except Exception as e:
                logger.error(f"Error fetching RSS feed {feed_url}: {str(e)}")
                continue
        
        return list(set(all_urls))  # Remove duplicates
    
    async def run(self) -> List[OpportunityHackGrant]:
        """Run the grant finder."""
        logger.info("Starting Opportunity Hack Grant Finder")
        self.grants_found = []
        
        # Collect all URLs to crawl
        urls_to_crawl = self.direct_urls.copy()
        
        # Google search if enabled
        if self.use_google_search:
            logger.info("Searching with Google...")
            search_urls = await self.search_with_google()
            urls_to_crawl.extend(search_urls)
            logger.info(f"Found {len(search_urls)} URLs from Google search")
        else:
            logger.info("Skipping Google search as it's disabled")
        
        # RSS feeds if enabled
        if self.use_rss_feeds:
            logger.info("Fetching RSS feeds...")
            rss_urls = await self.fetch_rss_feeds()
            urls_to_crawl.extend(rss_urls)
            logger.info(f"Found {len(rss_urls)} URLs from RSS feeds")
        
        # Remove duplicates
        urls_to_crawl = list(set(urls_to_crawl))
        logger.info(f"Starting crawl with {len(urls_to_crawl)} seed URLs")
        
        # Use our advanced crawler with our page processor
        # Note: The process_page method now handles adding to self.grants_found
        # and incremental saving, so we don't need to do that here anymore
        await self.crawler.crawl(
            urls_to_crawl, 
            self.process_page
        )
        
        # Ensure any remaining unsaved grants are saved
        if self.incremental_save:
            logger.info("Saving any remaining grants...")
            await self.save_pending_grants()
        
        # Sort by relevance score
        self.grants_found.sort(key=lambda x: x.relevance_score, reverse=True)
        
        logger.info(f"Found {len(self.grants_found)} grant opportunities, saved {self.grants_saved_count} incrementally")
        return self.grants_found
    
    def save_results(self, output_dir: Path = OUTPUT_DIR) -> Tuple[Path, Path]:
        """Save grant findings to JSON and CSV."""
        # If we're using incremental saving, just finalize the existing files
        if self.incremental_save:
            # Finalize JSON file by closing the array
            with open(self.json_path, 'a', encoding='utf-8') as f:
                f.write('\n]')
                
            logger.info(f"Finalized incremental results in {self.json_path} and {self.csv_path}")
            return self.json_path, self.csv_path
        
        # Otherwise, perform regular save
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save to JSON
        json_path = output_dir / f"opportunity_hack_grants_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump([grant.to_dict() for grant in self.grants_found], f, indent=2, ensure_ascii=False)
        
        # Save to CSV
        csv_path = output_dir / f"opportunity_hack_grants_{timestamp}.csv"
        
        # Prepare data for CSV
        csv_data = []
        for grant in self.grants_found:
            csv_data.append(self._prepare_csv_data(grant))
        
        # Create DataFrame and save
        df = pd.DataFrame(csv_data)
        df.to_csv(csv_path, index=False)
        
        logger.info(f"Results saved to {json_path} and {csv_path}")
        return json_path, csv_path
        
    def get_unsaved_grants(self) -> List[OpportunityHackGrant]:
        """Get grants that haven't been saved yet."""
        if not self.incremental_save:
            return self.grants_found
        
        # Return only grants that haven't been saved yet
        return self.grants_found[self.grants_saved_count:]
        
    async def save_pending_grants(self) -> None:
        """Save any pending grants that haven't been saved yet."""
        if not self.incremental_save:
            return
            
        unsaved_grants = self.get_unsaved_grants()
        for grant in unsaved_grants:
            await self.save_grant_incrementally(grant)

# These utility functions have been moved to their respective utility modules:
# - src/utils/email_utils.py: send_email_notification
# - src/utils/reporting.py: generate_summary_report

# The main entry point has been moved to main.py
# This module is now focused on providing the grant finder functionality