"""
Optimized web crawler module for the Opportunity Hack Grant Finder.

This module provides a high-performance, concurrent web crawler designed 
specifically for finding grant opportunities. It respects robots.txt, 
handles rate limiting, and uses various techniques to avoid being blocked.
"""

import asyncio
import json
import logging
import random
import re
import time
from asyncio import Semaphore
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, DefaultDict
from urllib.parse import urljoin, urlparse

import aiohttp
import aiohttp_retry
from aiohttp import ClientSession, ClientTimeout
from aiohttp_retry import RetryClient, ExponentialRetry
from bs4 import BeautifulSoup

from src.config import (
    CRAWLER_CONFIG, URL_BLOCKLIST, USER_AGENTS, 
    CACHE_DIR, VISUAL_CONFIG, DOMAIN_SPECIFIC_CONFIGS
)

# Configure logger
logger = logging.getLogger("crawler")

class CacheManager:
    """Manages caching of crawled URLs to avoid redundant requests."""
    
    def __init__(self, cache_dir: Path = CACHE_DIR, expiry_seconds: int = CRAWLER_CONFIG["cache_expiry"]):
        """Initialize the cache manager."""
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.expiry_seconds = expiry_seconds
        self.memory_cache: Dict[str, dict] = {}
        
    def _get_cache_file_path(self, url: str) -> Path:
        """Get the cache file path for a URL."""
        import hashlib
        # Create a hash of the URL to use as the filename
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.json"
    
    async def get(self, url: str) -> Optional[dict]:
        """Get cached data for a URL if it exists and is not expired."""
        # Check memory cache first
        if url in self.memory_cache:
            cached_data = self.memory_cache[url]
            cached_time = datetime.fromisoformat(cached_data['timestamp'])
            if datetime.now() - cached_time < timedelta(seconds=self.expiry_seconds):
                return cached_data
            else:
                # Expired from memory cache
                del self.memory_cache[url]
        
        # Check disk cache
        cache_file = self._get_cache_file_path(url)
        if cache_file.exists():
            try:
                # Read the cache file directly instead of using aiohttp which can't handle file:// URLs properly
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    
                cached_time = datetime.fromisoformat(cached_data['timestamp'])
                
                # Check if cache is expired
                if datetime.now() - cached_time < timedelta(seconds=self.expiry_seconds):
                    # Add to memory cache
                    self.memory_cache[url] = cached_data
                    logger.debug(f"Cache hit for {url}")
                    return cached_data
                else:
                    # Cache is expired, remove file
                    cache_file.unlink(missing_ok=True)
                    return None
            except Exception as e:
                logger.warning(f"Error reading cache for {url}: {str(e)}")
                # Remove potentially corrupt cache file
                cache_file.unlink(missing_ok=True)
                return None
        
        return None
    
    async def set(self, url: str, data: dict) -> None:
        """Cache data for a URL."""
        # Add timestamp to the data
        data['timestamp'] = datetime.now().isoformat()
        
        # Update memory cache
        self.memory_cache[url] = data
        
        # Update disk cache
        cache_file = self._get_cache_file_path(url)
        try:
            # Make sure the parent directory exists
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write cache directly to file instead of using aiohttp for local file operations
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
            except (IOError, PermissionError) as e:
                logger.warning(f"Cache write permission error for {url}: {str(e)}")
            except UnicodeEncodeError as e:
                logger.warning(f"Cache encoding error for {url}: {str(e)}")
        except Exception as e:
            logger.warning(f"Error writing cache for {url}: {type(e).__name__}: {str(e)}")

class RobotsParser:
    """Handles robots.txt parsing and checking for allowed URLs."""
    
    def __init__(self, respect_robots: bool = CRAWLER_CONFIG["respect_robots_txt"]):
        """Initialize the robots parser."""
        self.respect_robots = respect_robots
        self.robots_cache: Dict[str, Dict[str, Set[str]]] = {}  # domain -> {user_agent -> disallowed paths}
        self.user_agent = USER_AGENTS[0]  # Default user agent
    
    async def is_allowed(self, url: str, user_agent: str) -> bool:
        """Check if a URL is allowed by robots.txt."""
        if not self.respect_robots:
            return True
            
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        path = parsed_url.path
        
        # Get robots rules from cache or create new one
        if domain not in self.robots_cache:
            try:
                robots_url = f"{parsed_url.scheme}://{domain}/robots.txt"
                self.robots_cache[domain] = await self._fetch_robots(robots_url)
            except Exception as e:
                logger.warning(f"Error fetching robots.txt for {domain}: {str(e)}")
                return True  # Allow if we can't fetch robots.txt
        
        # Check if URL is allowed
        try:
            # Find matching user agent
            user_agent_lower = user_agent.lower()
            agent_rules = None
            
            # Try to find exact match for user agent
            for agent in self.robots_cache[domain]:
                if agent.lower() in user_agent_lower:
                    agent_rules = self.robots_cache[domain][agent]
                    break
            
            # If no exact match, try wildcard
            if agent_rules is None and '*' in self.robots_cache[domain]:
                agent_rules = self.robots_cache[domain]['*']
            
            # If no rules found, allow
            if agent_rules is None:
                return True
                
            # Check if path is disallowed
            for disallowed_path in agent_rules:
                if path.startswith(disallowed_path):
                    return False
                
            return True
        except Exception as e:
            logger.warning(f"Error checking robots.txt for {url}: {str(e)}")
            return True  # Allow if there's an error checking
    
    async def _fetch_robots(self, robots_url: str) -> Dict[str, Set[str]]:
        """Fetch and parse robots.txt."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(robots_url) as response:
                    if response.status == 200:
                        robots_content = await response.text()
                        return self._parse_robots_txt(robots_content)
                    else:
                        # If robots.txt doesn't exist or can't be retrieved, return empty rules
                        return {}
        except Exception as e:
            logger.warning(f"Error fetching robots.txt from {robots_url}: {str(e)}")
            return {}
            
    def _parse_robots_txt(self, content: str) -> Dict[str, Set[str]]:
        """Parse robots.txt content into a dict of user agents and disallowed paths."""
        rules = {}
        current_agent = None
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
                
            # Check for User-agent
            if line.lower().startswith('user-agent:'):
                agent = line[11:].strip()
                current_agent = agent
                if current_agent not in rules:
                    rules[current_agent] = set()
            
            # Check for Disallow
            elif line.lower().startswith('disallow:') and current_agent:
                path = line[9:].strip()
                if path:
                    rules[current_agent].add(path)
                    
            # Check for Allow (we ignore allows as a conservative approach)
            # elif line.lower().startswith('allow:'):
            #     path = line[6:].strip()
            #     if path and current_agent:
            #         rules[current_agent]['allowed'].add(path)
        
        return rules

class DomainRateLimiter:
    """Manages rate limiting per domain to avoid overloading servers."""
    
    def __init__(
        self, 
        max_per_domain: int = CRAWLER_CONFIG["max_concurrent_per_domain"],
        delay_range: Tuple[float, float] = CRAWLER_CONFIG["random_delay_range"]
    ):
        """Initialize the rate limiter."""
        self.max_per_domain = max_per_domain
        self.delay_range = delay_range
        self.domain_semaphores: Dict[str, Semaphore] = {}
        self.last_request_time: Dict[str, float] = {}
        self.domain_settings: Dict[str, Dict[str, Any]] = {}
    
    def get_domain_config(self, url: str) -> Optional[Dict[str, Any]]:
        """Get domain-specific configuration for a URL if it exists."""
        domain = urlparse(url).netloc
        
        # Return cached config if available
        if domain in self.domain_settings:
            return self.domain_settings[domain]
        
        # Check exact domain match first
        if domain in DOMAIN_SPECIFIC_CONFIGS:
            self.domain_settings[domain] = DOMAIN_SPECIFIC_CONFIGS[domain]
            return self.domain_settings[domain]
        
        # Check for parent domain match (e.g., subdomain.example.com matches example.com)
        domain_parts = domain.split('.')
        for i in range(1, len(domain_parts) - 1):
            parent_domain = '.'.join(domain_parts[i:])
            if parent_domain in DOMAIN_SPECIFIC_CONFIGS:
                self.domain_settings[domain] = DOMAIN_SPECIFIC_CONFIGS[parent_domain]
                return self.domain_settings[domain]
        
        # No specific config found
        self.domain_settings[domain] = None
        return None
    
    def get_semaphore(self, url: str) -> Semaphore:
        """Get or create a semaphore for a domain."""
        domain = urlparse(url).netloc
        if domain not in self.domain_semaphores:
            # Check for domain-specific concurrent settings
            domain_config = self.get_domain_config(url)
            max_concurrent = domain_config.get("max_concurrent", self.max_per_domain) if domain_config else self.max_per_domain
            self.domain_semaphores[domain] = Semaphore(max_concurrent)
        return self.domain_semaphores[domain]
    
    async def acquire(self, url: str) -> None:
        """Acquire a semaphore for a domain and respect rate limiting."""
        domain = urlparse(url).netloc
        semaphore = self.get_semaphore(url)
        
        # Acquire semaphore
        await semaphore.acquire()
        
        # Get domain-specific delay settings
        domain_config = self.get_domain_config(url)
        current_delay_range = domain_config.get("delay_range", self.delay_range) if domain_config else self.delay_range
        
        # Apply rate limiting delay if needed
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]
            delay = random.uniform(current_delay_range[0], current_delay_range[1])
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
        
        # Update last request time
        self.last_request_time[domain] = time.time()
    
    def release(self, url: str) -> None:
        """Release a semaphore for a domain."""
        domain = urlparse(url).netloc
        if domain in self.domain_semaphores:
            self.domain_semaphores[domain].release()

class DomainQueueManager:
    """Manages URL queues on a per-domain basis with customizable crawling strategies."""
    
    def __init__(self):
        """Initialize the domain queue manager."""
        self.domain_queues: Dict[str, List[Tuple[str, int]]] = {}  # domain -> list of (url, depth) tuples
        self.domain_visited: Dict[str, Set[str]] = {}  # domain -> set of visited URLs
        self.domain_counts: Dict[str, int] = {}  # domain -> count of pages visited
        self.global_queue = asyncio.Queue()  # Fallback queue for standard processing
        self.domain_configs = {}  # Cached domain configs
        
    def get_domain_config(self, url: str) -> Optional[Dict[str, Any]]:
        """Get domain-specific configuration for a URL if it exists."""
        domain = urlparse(url).netloc
        
        # Check exact domain match first
        if domain in DOMAIN_SPECIFIC_CONFIGS:
            return DOMAIN_SPECIFIC_CONFIGS[domain]
        
        # Check for parent domain match (e.g., subdomain.example.com matches example.com)
        domain_parts = domain.split('.')
        for i in range(1, len(domain_parts) - 1):
            parent_domain = '.'.join(domain_parts[i:])
            if parent_domain in DOMAIN_SPECIFIC_CONFIGS:
                return DOMAIN_SPECIFIC_CONFIGS[parent_domain]
        
        return None
    
    def should_queue_url(self, url: str, depth: int) -> bool:
        """Determine if a URL should be queued based on domain-specific rules."""
        domain = urlparse(url).netloc
        
        # Initialize domain structures if not already done
        if domain not in self.domain_visited:
            self.domain_visited[domain] = set()
        if domain not in self.domain_counts:
            self.domain_counts[domain] = 0
            
        # Check if URL already visited
        if url in self.domain_visited[domain]:
            return False
            
        # Get domain config if available
        domain_config = self.get_domain_config(url)
        if domain_config:
            # Check domain-specific URL blocklist
            if "url_blocklist" in domain_config:
                for pattern in domain_config["url_blocklist"]:
                    if pattern in url:
                        return False
            
            # Check max pages limit
            if self.domain_counts[domain] >= domain_config.get("max_pages", float('inf')):
                return False
                
            # Check max depth
            if depth > domain_config.get("max_depth", CRAWLER_CONFIG["max_depth"]):
                return False
                
        return True
    
    def add_url(self, url: str, depth: int) -> None:
        """Add a URL to the appropriate queue."""
        if not self.should_queue_url(url, depth):
            return
            
        domain = urlparse(url).netloc
        
        # Initialize domain queue if needed
        if domain not in self.domain_queues:
            self.domain_queues[domain] = []
            
        # Add to domain-specific queue
        self.domain_queues[domain].append((url, depth))
        
        # Mark as visited (to avoid duplicates)
        if domain not in self.domain_visited:
            self.domain_visited[domain] = set()
        self.domain_visited[domain].add(url)
    
    def prioritize_url(self, url: str) -> float:
        """Calculate a priority score for a URL based on domain-specific rules."""
        domain = urlparse(url).netloc
        domain_config = self.get_domain_config(url)
        
        # Default priority
        priority = 0.0
        
        if domain_config:
            # Boost priority for content patterns
            if "content_patterns" in domain_config:
                for pattern in domain_config["content_patterns"]:
                    if pattern in url:
                        priority += 1.0
                        
            # Adjust for depth/breadth preference
            if domain_config.get("depth_priority", False):
                # For depth-first, we want higher depth to have higher priority
                # We'll use a negative score so that deeper URLs get popped first
                parsed_path = urlparse(url).path
                depth_score = -len(parsed_path.split('/'))
                priority += depth_score
        
        return priority
    
    def get_next_url(self) -> Optional[Tuple[str, int]]:
        """Get the next URL to crawl based on priorities."""
        # Find non-empty domain queues
        available_domains = [d for d, q in self.domain_queues.items() if q]
        
        if not available_domains:
            return None
            
        # Select domain with highest priority URL
        selected_domain = None
        selected_url_data = None
        highest_priority = float('-inf')
        
        for domain in available_domains:
            if not self.domain_queues[domain]:
                continue
                
            # Get domain config to check for depth-first or breadth-first
            domain_config = self.get_domain_config(domain)
            
            # Determine URL selection strategy
            if domain_config and domain_config.get("depth_priority", False):
                # Sort by path depth (for depth-first)
                sorted_urls = sorted(
                    self.domain_queues[domain],
                    key=lambda x: (
                        -len(urlparse(x[0]).path.split('/')),  # Deeper paths first
                        self.prioritize_url(x[0])  # Then by content patterns
                    )
                )
                url_data = sorted_urls[0] if sorted_urls else None
            else:
                # Use breadth-first (default)
                urls_with_priority = [
                    (u, d, self.prioritize_url(u)) 
                    for u, d in self.domain_queues[domain]
                ]
                sorted_urls = sorted(urls_with_priority, key=lambda x: x[2], reverse=True)
                url_data = (sorted_urls[0][0], sorted_urls[0][1]) if sorted_urls else None
            
            if url_data:
                url_priority = self.prioritize_url(url_data[0])
                if url_priority > highest_priority:
                    highest_priority = url_priority
                    selected_domain = domain
                    selected_url_data = url_data
        
        if selected_domain and selected_url_data:
            # Remove from domain queue
            self.domain_queues[selected_domain].remove(selected_url_data)
            # Increment domain counter
            self.domain_counts[selected_domain] += 1
            return selected_url_data
            
        return None
    
    def queue_size(self) -> int:
        """Get total number of URLs queued across all domains."""
        return sum(len(q) for q in self.domain_queues.values())
    
    def queue_empty(self) -> bool:
        """Check if all domain queues are empty."""
        return all(len(q) == 0 for q in self.domain_queues.values())
    
    def get_domain_stats(self) -> Dict[str, Dict[str, int]]:
        """Get statistics about domain queues."""
        stats = {}
        for domain in self.domain_queues:
            stats[domain] = {
                "queued": len(self.domain_queues[domain]),
                "visited": len(self.domain_visited.get(domain, set())),
                "count": self.domain_counts.get(domain, 0)
            }
        return stats


class ProgressTracker:
    """Tracks and updates progress for the crawler."""
    
    def __init__(self, rich_console=None):
        """Initialize the progress tracker."""
        self.start_time = time.time()
        self.urls_found = 0
        self.urls_crawled = 0
        self.urls_failed = 0
        self.grants_found = 0
        self.domain_stats: DefaultDict[str, Dict[str, int]] = defaultdict(lambda: {"crawled": 0, "queued": 0, "failed": 0})
        self.rich_console = rich_console
        self.last_update_time = time.time()
        self.progress_tasks = {}
        
    def url_found(self, url: str) -> None:
        """Track a URL that's been found."""
        self.urls_found += 1
        domain = urlparse(url).netloc
        self.domain_stats[domain]["queued"] += 1
        self._update_display()
    
    def url_crawled(self, url: str, success: bool = True) -> None:
        """Track a URL that's been crawled."""
        if success:
            self.urls_crawled += 1
            domain = urlparse(url).netloc
            self.domain_stats[domain]["crawled"] += 1
            self.domain_stats[domain]["queued"] -= 1
        else:
            self.urls_failed += 1
            domain = urlparse(url).netloc
            self.domain_stats[domain]["failed"] += 1
            self.domain_stats[domain]["queued"] -= 1
        self._update_display()
    
    def grant_found(self) -> None:
        """Track a grant that's been found."""
        self.grants_found += 1
        self._update_display()
    
    def _update_display(self) -> None:
        """Update the display with current progress."""
        if not VISUAL_CONFIG["use_rich_display"] or not self.rich_console:
            return
            
        # Only update at certain intervals to avoid slowing down
        if time.time() - self.last_update_time < VISUAL_CONFIG["update_interval"]:
            return
            
        self.last_update_time = time.time()
        
        # Create a pretty display
        if VISUAL_CONFIG["show_status_panel"]:
            elapsed = time.time() - self.start_time
            rate = self.urls_crawled / elapsed if elapsed > 0 else 0
            
            # Basic stats
            self.rich_console.print(f"[{VISUAL_CONFIG['color_scheme']['title']}]Crawler Status:[/{VISUAL_CONFIG['color_scheme']['title']}]")
            self.rich_console.print(f"URLs Found: {self.urls_found}")
            self.rich_console.print(f"URLs Crawled: {self.urls_crawled}")
            self.rich_console.print(f"URLs Failed: {self.urls_failed}")
            self.rich_console.print(f"Grants Found: [{VISUAL_CONFIG['color_scheme']['highlight']}]{self.grants_found}[/{VISUAL_CONFIG['color_scheme']['highlight']}]")
            self.rich_console.print(f"Rate: {rate:.2f} URLs/sec")
            self.rich_console.print(f"Elapsed: {timedelta(seconds=int(elapsed))}")
            
            # Domain stats if enabled
            if VISUAL_CONFIG["show_domain_progress"]:
                self.rich_console.print(f"\n[{VISUAL_CONFIG['color_scheme']['title']}]Domain Stats:[/{VISUAL_CONFIG['color_scheme']['title']}]")
                for domain, stats in sorted(
                    self.domain_stats.items(), 
                    key=lambda x: x[1]["crawled"] + x[1]["queued"] + x[1]["failed"], 
                    reverse=True
                )[:10]:  # Show top 10 domains
                    self.rich_console.print(f"{domain}: Crawled: {stats['crawled']}, Queued: {stats['queued']}, Failed: {stats['failed']}")

class AdvancedCrawler:
    """Advanced web crawler with parallel processing and intelligent traversal."""
    
    def __init__(
        self,
        max_concurrent_requests: int = CRAWLER_CONFIG["max_concurrent_requests"],
        max_depth: int = CRAWLER_CONFIG["max_depth"],
        respect_robots_txt: bool = CRAWLER_CONFIG["respect_robots_txt"],
        follow_redirects: bool = CRAWLER_CONFIG["follow_redirects"],
        verify_ssl: bool = CRAWLER_CONFIG["verify_ssl"],
        timeout: int = CRAWLER_CONFIG["timeout"],
        max_retry_attempts: int = CRAWLER_CONFIG["max_retry_attempts"],
        max_urls_per_run: int = CRAWLER_CONFIG["max_urls_per_run"],
        chunk_size: int = CRAWLER_CONFIG["chunk_size"],
        rich_console = None
    ):
        """Initialize the advanced crawler."""
        self.max_concurrent_requests = max_concurrent_requests
        self.max_depth = max_depth
        self.respect_robots_txt = respect_robots_txt
        self.follow_redirects = follow_redirects
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.max_retry_attempts = max_retry_attempts
        self.max_urls_per_run = max_urls_per_run
        self.chunk_size = chunk_size
        
        # Initialize components
        self.cache_manager = CacheManager()
        self.robots_parser = RobotsParser(respect_robots_txt)
        self.rate_limiter = DomainRateLimiter()
        self.progress_tracker = ProgressTracker(rich_console)
        self.domain_queue_manager = DomainQueueManager()  # New domain-specific queue manager
        
        # State
        self.visited_urls: Set[str] = set()
        self.visit_queue: asyncio.Queue = asyncio.Queue()
        self.global_semaphore = Semaphore(max_concurrent_requests)
        self.results = []
        self.crawl_tasks = []
        
        # Event to signal crawler to stop
        self.stop_event = asyncio.Event()
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the configured list."""
        return random.choice(USER_AGENTS)
    
    def _is_valid_url(self, url: str) -> bool:
        """Check if a URL is valid and should be crawled."""
        # Basic URL validation
        if not url or not url.startswith(('http://', 'https://')):
            return False
            
        # Check against global blocklist
        parsed_url = urlparse(url)
        for blocked in URL_BLOCKLIST:
            if blocked in url:
                return False
        
        # Check domain-specific blocklist
        domain_config = self.domain_queue_manager.get_domain_config(url)
        if domain_config and "url_blocklist" in domain_config:
            for pattern in domain_config["url_blocklist"]:
                if pattern in url:
                    return False
                
        # Filter out common non-textual content
        if re.search(r'\.(jpg|jpeg|png|gif|bmp|svg|webp|mp4|mp3|wav|pdf|zip|tar|gz|rar)$', parsed_url.path, re.IGNORECASE):
            return False
                        
        return True
    
    async def get_session(self) -> RetryClient:
        """Create an aiohttp session with retry capability."""
        retry_options = ExponentialRetry(
            attempts=self.max_retry_attempts,
            start_timeout=1,
            max_timeout=10,
            factor=2.0
        )
        
        timeout = ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': self._get_random_user_agent()}
        )
        
        return RetryClient(session, retry_options=retry_options)
    
    async def fetch_url(self, url: str, depth: int, session: RetryClient) -> Optional[Tuple[str, str]]:
        """Fetch a URL with appropriate rate limiting and caching."""
        # Check cache first
        cached_data = await self.cache_manager.get(url)
        if cached_data:
            logger.debug(f"Cache hit for {url}")
            return url, cached_data['html']
            
        # Get user agent
        user_agent = self._get_random_user_agent()
        
        # Check robots.txt
        if not await self.robots_parser.is_allowed(url, user_agent):
            logger.info(f"Robots.txt disallows {url}")
            return None
            
        # Apply rate limiting
        try:
            await self.rate_limiter.acquire(url)
            
            # Use a semaphore to limit concurrent requests
            async with self.global_semaphore:
                try:
                    # Set headers with random user agent
                    headers = {'User-Agent': user_agent}
                    
                    # Make request
                    async with session.get(
                        url,
                        allow_redirects=self.follow_redirects,
                        headers=headers
                    ) as response:
                        if response.status == 200:
                            # Check content type
                            content_type = response.headers.get('Content-Type', '')
                            if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
                                logger.debug(f"Skipping non-HTML content: {url} ({content_type})")
                                return None
                                
                            # Check content length
                            content_length = int(response.headers.get('Content-Length', '0'))
                            if content_length > CRAWLER_CONFIG["max_content_length"]:
                                logger.debug(f"Skipping large content: {url} ({content_length} bytes)")
                                return None
                                
                            # Get HTML content
                            html = await response.text()
                            
                            # Cache the result
                            await self.cache_manager.set(url, {'html': html})
                            
                            return url, html
                        elif response.status == 404:
                            # For 404 errors, try to crawl the root domain if enabled
                            if CRAWLER_CONFIG["crawl_root_on_404"]:
                                parsed_url = urlparse(url)
                                root_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
                                
                                # Only queue the root if it's not the current URL and not already visited
                                if root_url != url and root_url not in self.visited_urls:
                                    logger.info(f"Page not found: {url} - Queuing root domain: {root_url}")
                                    await self.visit_queue.put((root_url, depth))
                            
                            return None
                        else:
                            logger.warning(f"Failed to fetch {url}: Status {response.status}")
                            return None
                except Exception as e:
                    logger.error(f"Error fetching {url}: {str(e)}")
                    return None
        finally:
            # Always release the rate limiter
            self.rate_limiter.release(url)
    
    async def extract_links(self, url: str, html: str) -> Set[str]:
        """Extract and normalize links from HTML content."""
        links = set()
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract links from <a> tags
            for link in soup.find_all('a', href=True):
                href = link['href']
                absolute_url = urljoin(url, href)
                
                # Validate URL
                if self._is_valid_url(absolute_url):
                    links.add(absolute_url)
            
            # Extract links from <link> tags (useful for pagination)
            for link in soup.find_all('link', href=True, rel=re.compile(r'next|alternate')):
                href = link['href']
                absolute_url = urljoin(url, href)
                
                # Validate URL
                if self._is_valid_url(absolute_url):
                    links.add(absolute_url)
                    
            # Extract links from canonical and alternate URLs
            for link in soup.find_all('link', href=True, rel=re.compile(r'canonical|alternate')):
                href = link['href']
                absolute_url = urljoin(url, href)
                
                # Validate URL
                if self._is_valid_url(absolute_url):
                    links.add(absolute_url)
        except Exception as e:
            logger.error(f"Error extracting links from {url}: {str(e)}")
        
        return links
    
    async def process_url(self, url: str, depth: int, session: RetryClient, process_callback) -> None:
        """Process a URL by fetching it, extracting links, and processing content."""
        try:
            # Track URL
            self.progress_tracker.url_found(url)
            
            # Skip if already visited
            if url in self.visited_urls:
                return
                
            self.visited_urls.add(url)
            
            # Get domain-specific config if available
            domain = urlparse(url).netloc
            domain_config = self.domain_queue_manager.get_domain_config(url)
            
            # Apply domain-specific rate limiting if configured
            if domain_config and "delay_range" in domain_config:
                # Override the global rate limiter for this domain
                old_delay = self.rate_limiter.delay_range
                self.rate_limiter.delay_range = domain_config["delay_range"]
                
            # Fetch URL
            result = await self.fetch_url(url, depth, session)
            
            # Restore original delay range if it was changed
            if domain_config and "delay_range" in domain_config:
                self.rate_limiter.delay_range = old_delay
                
            if not result:
                self.progress_tracker.url_crawled(url, success=False)
                return
                
            url, html = result
            
            # Apply content filters from domain-specific config
            if domain_config and "content_filters" in domain_config:
                content_filters = domain_config["content_filters"]
                
                # Check minimum content length
                if "min_content_length" in content_filters and len(html) < content_filters["min_content_length"]:
                    logger.debug(f"Skipping {url} due to insufficient content length")
                    self.progress_tracker.url_crawled(url, success=False)
                    return
                
                # Check required keywords
                if "require_keywords" in content_filters:
                    html_lower = html.lower()
                    if not any(keyword.lower() in html_lower for keyword in content_filters["require_keywords"]):
                        logger.debug(f"Skipping {url} due to missing required keywords")
                        self.progress_tracker.url_crawled(url, success=False)
                        return
            
            # Process content using callback
            try:
                process_result = await process_callback(url, html, depth)
                if process_result:
                    self.results.append(process_result)
                    self.progress_tracker.grant_found()
            except Exception as e:
                logger.error(f"Error processing content from {url}: {str(e)}")
            
            # Extract links if not at max depth
            max_depth = domain_config.get("max_depth", self.max_depth) if domain_config else self.max_depth
            if depth < max_depth:
                links = await self.extract_links(url, html)
                
                # Add links to appropriate queue based on domain
                for link in links:
                    if link not in self.visited_urls:
                        link_domain = urlparse(link).netloc
                        
                        # Check if this is a domain we're managing specifically
                        if self.domain_queue_manager.get_domain_config(link):
                            # Add to domain-specific queue
                            self.domain_queue_manager.add_url(link, depth + 1)
                        else:
                            # Add to regular queue
                            await self.visit_queue.put((link, depth + 1))
            
            # Mark as crawled
            self.progress_tracker.url_crawled(url, success=True)
            
        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}")
            self.progress_tracker.url_crawled(url, success=False)
    
    async def crawl_worker(self, worker_id: int, session: RetryClient, process_callback) -> None:
        """Worker that continuously processes URLs from the queue."""
        logger.debug(f"Crawler worker {worker_id} started")
        
        try:
            while not self.stop_event.is_set():
                try:
                    # Try to get URL from domain queue manager first (for domain-specific strategies)
                    url_data = self.domain_queue_manager.get_next_url()
                    
                    if url_data:
                        url, depth = url_data
                    else:
                        # If domain queue is empty, try regular queue with timeout
                        try:
                            url, depth = await asyncio.wait_for(self.visit_queue.get(), timeout=1.0)
                        except asyncio.TimeoutError:
                            # Both queues empty, check if we should exit
                            if self.visit_queue.empty() and self.domain_queue_manager.queue_empty() and all(t.done() for t in self.crawl_tasks):
                                break
                            continue
                    
                    # Process URL
                    await self.process_url(url, depth, session, process_callback)
                    
                    # Mark task as done if it came from the regular queue
                    if not url_data:  # url came from visit_queue
                        self.visit_queue.task_done()
                    
                    # Check if we've reached the URL limit
                    if len(self.visited_urls) >= self.max_urls_per_run:
                        logger.info(f"Reached maximum URLs per run: {self.max_urls_per_run}")
                        self.stop_event.set()
                        break
                        
                except Exception as e:
                    logger.error(f"Error in crawler worker {worker_id}: {str(e)}")
        except asyncio.CancelledError:
            logger.debug(f"Crawler worker {worker_id} cancelled")
        
        logger.debug(f"Crawler worker {worker_id} finished")
    
    async def crawl(self, start_urls: List[str], process_callback) -> List[Any]:
        """Start crawling from a list of URLs and process pages with a callback function."""
        logger.info(f"Starting crawler with {len(start_urls)} seed URLs")
        self.results = []
        self.visited_urls = set()
        self.visit_queue = asyncio.Queue()
        self.stop_event.clear()
        
        # Initialize a new domain queue manager
        self.domain_queue_manager = DomainQueueManager()
        
        # Add start URLs to appropriate queues
        for url in start_urls:
            if self._is_valid_url(url):
                # Check if this URL belongs to a domain with specific config
                if self.domain_queue_manager.get_domain_config(url):
                    # Add to domain-specific queue
                    self.domain_queue_manager.add_url(url, 0)
                    logger.info(f"Added {url} to domain-specific queue")
                else:
                    # Add to regular queue
                    await self.visit_queue.put((url, 0))
        
        # Log domain-specific queue statistics
        domain_stats = self.domain_queue_manager.get_domain_stats()
        for domain, stats in domain_stats.items():
            logger.info(f"Domain {domain}: {stats['queued']} URLs queued with domain-specific settings")
            config = self.domain_queue_manager.get_domain_config(f"https://{domain}/")
            if config:
                logger.info(f"  - Max pages: {config.get('max_pages', 'unlimited')}")
                logger.info(f"  - Max depth: {config.get('max_depth', self.max_depth)}")
                logger.info(f"  - Strategy: {'Depth-first' if config.get('depth_priority', False) else 'Breadth-first'}")
        
        # Create session
        async with await self.get_session() as session:
            # Start worker tasks
            worker_count = self.max_concurrent_requests
            self.crawl_tasks = [
                asyncio.create_task(self.crawl_worker(i, session, process_callback))
                for i in range(worker_count)
            ]
            
            # Wait for all workers to finish
            try:
                await asyncio.gather(*self.crawl_tasks)
            except Exception as e:
                logger.error(f"Error in crawl tasks: {str(e)}")
                # Cancel any remaining tasks
                for task in self.crawl_tasks:
                    if not task.done():
                        task.cancel()
        
        # Gather domain-specific statistics for the final report
        domain_stats = self.domain_queue_manager.get_domain_stats()
        for domain, stats in domain_stats.items():
            logger.info(f"Domain {domain}: Visited {stats['count']} URLs with domain-specific settings")
        
        logger.info(f"Crawler finished. Visited {len(self.visited_urls)} URLs, found {len(self.results)} results.")
        return self.results
    
    def stop(self) -> None:
        """Signal the crawler to stop."""
        self.stop_event.set()