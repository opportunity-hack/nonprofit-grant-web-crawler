# config.py
"""Configuration for Opportunity Hack Grant Finder."""

import os
import datetime
from pathlib import Path

# Load dot_env
from dotenv import load_dotenv
load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "opportunity_hack"
LOG_DIR = BASE_DIR / "logs"
CACHE_DIR = DATA_DIR / "cache"

# Ensure directories exist
for directory in [DATA_DIR, OUTPUT_DIR, LOG_DIR, CACHE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Crawler settings
CRAWLER_CONFIG = {
    "max_concurrent_requests": 30,        # Maximum number of concurrent requests
    "max_concurrent_per_domain": 5,       # Maximum concurrent requests per domain
    "rate_limit_delay": 1.4,              # Delay between requests in seconds
    "max_depth": 2,                       # Maximum crawl depth
    "max_retry_attempts": 2,              # Maximum retry attempts for failed requests
    "use_google_search": True,            # Use Google Custom Search
    "use_rss_feeds": True,                # Use RSS feeds
    "respect_robots_txt": True,           # Respect robots.txt
    "random_delay_range": (0.7, 2.1),     # Random delay range to avoid detection
    "timeout": 10,                        # Request timeout in seconds
    "cache_expiry": 86400,                # Cache expiry in seconds (24 hours)
    "user_agent_rotation": True,          # Rotate user agents
    "follow_redirects": True,             # Follow redirects
    "verify_ssl": False,                  # Verify SSL certificates
    "chunk_size": 50,                     # TODO: Process URLs in chunks for memory efficiency
    "max_urls_per_run": 5000,             # Maximum URLs to process per run
    "max_content_length": 5 * 1024 * 1024,# Maximum content length to process (5MB)
    "crawl_root_on_404": True,            # When a 404 is encountered, try to crawl the root domain
    "incremental_save": True,             # Save results incrementally during crawling
    "save_interval": 50,                  # Save after every N grant discoveries (0 = only at end)
    "append_results": True,               # Append to existing files rather than overwriting
}

# Relevance scoring
RELEVANCE_CONFIG = {
    "min_score": 0.35,                     # Minimum relevance score (0.0 to 1.0)
    "high_relevance_threshold": 0.7,      # Threshold for high relevance
    "auto_grant_threshold": 0.65,         # Threshold for auto-grant writing
    "title_match_boost": 0.2,             # Boost score if keywords in title
    "description_match_boost": 0.1,       # Boost score if keywords in description
    "url_match_boost": 0.1,               # Boost score if keywords in URL
    "deadline_match_boost": 0.1,          # Boost score if deadline is found
    "funding_match_boost": 0.15,          # Boost score if funding amount is found
    "tech_match_boost": 0.01,             # Boost per tech skill match
    "opportunity_keywords_weight": 0.5,   # Weight for opportunity keywords
    "grant_signals_weight": 1.0,          # Weight for grant signals
}

# Keywords
OPPORTUNITY_HACK_KEYWORDS = [
    "arizona nonprofit technology",
    "arizona",
    "phoenix",
    "technology for social good",
    "hackathon funding",
    "tech volunteer",
    "coding for good",
    "nonprofit technology",
    "civic tech",
    "social impact technology",
    "digital inclusion",
    "nonprofit digital transformation",
    "tech skills-based volunteering",
    "capacity building technology",
    "nonprofit software development",
    "social innovation tech",
    "community tech",
    "tech4good",
    "tech for nonprofit",
]

# Grant signals - strong indicators of grant opportunities
GRANT_SIGNALS = [
    "grant application",
    "apply now",
    "application deadline",
    "submission deadline",
    "funding opportunity",
    "grant opportunity",
    "request for proposals",    
    "call for applications",
    "call for proposals",
    "notice of funding",
    "grant guidelines",
    "eligibility criteria",
    "selection criteria",
    "award amount",
    "funding amount",
    "grant period",
    "application process",
]

# Tech skills list
TECH_SKILLS = [
    # Programming languages
    "python", "javascript", "typescript", "react", "angular", "vue", "node.js", 
    "java", "kotlin", "scala", "c#", ".net", "php", "ruby", "go", "rust",
    
    # Mobile development
    "android", "ios", "swift", "flutter", "react native", "mobile development",
    
    # Web development
    "web development", "frontend", "backend", "full stack", "api", "rest",
    
    # Data science
    "data analysis", "data science", "machine learning", "ai", "artificial intelligence",
    "nlp", "natural language processing", "computer vision", "deep learning",
    
    # Design
    "ux design", "ui design", "user experience", "user interface", "design thinking",
    "product design", "interaction design",
    
    # DevOps and infrastructure
    "devops", "ci/cd", "continuous integration", "cloud", "aws", "azure", "gcp",
    "kubernetes", "docker", "containerization", "serverless",
    
    # Database
    "database", "sql", "nosql", "mongodb", "postgresql", "mysql", "redis",
    
    # Emerging tech
    "blockchain", "cybersecurity", "iot", "internet of things", "ar", "vr",
    "augmented reality", "virtual reality", "mixed reality",
    
    # Project management
    "product management", "project management", "agile", "scrum", "kanban",
]

# Nonprofit sectors
NONPROFIT_SECTORS = [
    # Core sectors
    "education", "healthcare", "environment", "poverty", "homelessness",
    "disaster relief", "human rights", "arts", "culture", "community development",
    "economic development", "youth", "elderly", "veterans", "disabilities",
    "mental health", "advocacy", "legal aid", "refugees", "immigration",
    
    # Additional sectors
    "food security", "hunger", "clean water", "sanitation", "affordable housing",
    "racial equity", "gender equality", "lgbtq+", "financial inclusion",
    "digital literacy", "workforce development", "child welfare", "public health",
    "substance abuse", "criminal justice", "climate change", "conservation",
    "renewable energy", "social justice", "civic engagement"
]

# Direct URLs to crawl (moved from opportunity_hack_grant_finder.py)
TARGET_URLS = [
    # Tech-for-Good Specific URLs
    "https://www.techsoup.org/community/grant-opportunities",
    "https://www.ffwd.org/tech-nonprofit-funding-opportunities/",
    "https://www.nten.org/funding/",
    "https://digitalimpactalliance.org/funding-opportunities/",
    "https://www.nethope.org/what-we-do/grants-and-funding-opportunities/",
    "https://www.techforgoodawards.com/grants",
    
    # Corporate Technology Grant Programs
    "https://www.google.org/impactchallenge/",
    "https://nonprofit.microsoft.com/en-us/grants",
    "https://www.cisco.com/c/en/us/about/csr/impact/cisco-foundation.html",
    "https://www.okta.com/okta-for-good/",
    "https://www.twilio.org/impact-fund/",
    "https://www.salesforce.org/grants/",
    "https://aws.amazon.com/government-education/nonprofits/",
    "https://www.intel.com/content/www/us/en/corporate-responsibility/grant-opportunities.html",
    
    # Hackathon & Innovation Funding
    "https://mlh.io/grants",
    "https://devpost.com/hackathons",
    "https://www.knightfoundation.org/grants",
    "https://solve.mit.edu/challenges",
    "https://www.globalinnovation.fund/apply/",
    "https://hackforla.org/donate/",

    "https://thelawrencefoundation.org/application-process/",
    "https://www.angelhack.com/angelhack-fund/",
    "https://www.hackerearth.com/challenges/",

    
    # Social Impact Funders
    "https://skoll.org/about/apply/",
    "https://omidyar.com/",
    "https://www.drkfoundation.org/apply-for-funding/",
    "https://mulagofoundation.org/how-we-fund",
    "https://echoinggreen.org/fellowship/",
    "https://www.ashoka.org/en-us/program/ashoka-venture-and-fellowship",
    
    # Government & Public Sector
    "https://beta.nsf.gov/funding/opportunities",
    "https://www.challenge.gov/",
    "https://www.grants.gov/web/grants/search-grants.html",
    "https://usdigitalresponse.org/governments/funding/",
    "https://www.usaid.gov/div",
    
    # Foundation Directories
    "https://candid.org/find-funding",
    "https://www.foundationcenter.org/find-funding",
    "https://www.grantstation.com/funding-resources",
    "https://grantspace.org/resources/knowledge-base/finding-grants/"
]

# Search queries for Google (moved from opportunity_hack_grant_finder.py)
SEARCH_QUERIES = [
    # Format: "main keywords" + "filetype:pdf" (for grant documents)
    "technology for social good grants",
    "hackathon funding nonprofit application",
    "tech volunteer grants nonprofit",
    "tech for good funding opportunity",
    "digital nonprofit grants application",

    # Arizona-specific searches
    "Arizona nonprofit technology grants",
    "Arizona tech for social good funding",
    "Arizona hackathon funding social impact",
    "Arizona coding for good grants",
    "Arizona nonprofit digital transformation funding",
    "Arizona tech skills-based volunteering grants",
    "Arizona capacity building technology grants",
    "Arizona nonprofit software development funding",
    "Arizona social innovation tech grants",
    "Arizona community tech funding",
    "Arizona tech4good grants",
    "Arizona tech for nonprofit funding",

    # Grant watch specific search terms that they might use
    "grant application technology for social good",
    "grant application hackathon funding",
    "grant application tech volunteer",
    "grant application coding for good",
    "grant application nonprofit technology",
    "grant application civic tech",
    "grant application social impact technology",
    "grant application digital inclusion",
    


    # Domain-specific searches
    "site:foundation.org nonprofit technology grants",
    "site:org technology for good funding",
    "site:edu technology for social impact funding",
    "site:gov tech nonprofit grants",
    "site:com hackathon funding opportunities",
    
    
    # Temporal relevance
    f"{datetime.datetime.now().year} nonprofit technology grants",
    f"{datetime.datetime.now().year} tech for social good funding",
    "upcoming hackathon funding social impact",
    "new grant technology nonprofit",
    f"{datetime.datetime.now().year} Arizona nonprofit technology grants",
    f"{datetime.datetime.now().year} Arizona tech for social good funding",
    "new Arizona hackathon funding social impact",
    "new Arizona coding for good grants",
    "new Arizona nonprofit digital transformation funding",
    "new Arizona tech skills-based volunteering grants",
    "new Arizona capacity building technology grants",
    
    # Combination queries
    "nonprofit technology grant application",
    "coding for good funding opportunity",
    "open source social impact funding",
    "hackathon social good grant",
]

# RSS feed URLs (moved from opportunity_hack_grant_finder.py)
RSS_FEEDS = [
    "https://www.grants.gov/rss/GG_NewOppByCategory.xml",
    "https://philanthropynewsdigest.org/feeds/rfps",
    "https://www.insidephilanthropy.com/home/feed",
    "https://grantstation.com/rss.xml",
    "https://www.grantcraft.org/feed/",
    "https://www.fundsforngos.org/feed/",
    "https://www.thecatalyst.org/rss",
    "https://ssir.org/rss/",
]

# Social media API configurations
SOCIAL_MEDIA_CONFIG = {
    "twitter_enabled": False,  # Set to True when credentials are configured
    "twitter_api_key": os.getenv("TWITTER_API_KEY", ""),
    "twitter_api_secret": os.getenv("TWITTER_API_SECRET", ""),
    "twitter_access_token": os.getenv("TWITTER_ACCESS_TOKEN", ""),
    "twitter_access_secret": os.getenv("TWITTER_ACCESS_SECRET", ""),
    "twitter_search_queries": [
        "#TechForGood grants",
        "#NonprofitTech funding",
        "#SocialImpact technology grant",
        "#TechNonprofit opportunity",
        "tech grants for nonprofits",
    ],
    "twitter_accounts_to_follow": [
        "techforgood",
        "techsoup",
        "NetHope",
        "digitalimpact",
        "knightfdn",
        "gatesfoundation",
        "fordfoundation",
        "RockefellerFdn",
    ]
}

# Blocklist for URLs that should be ignored
URL_BLOCKLIST = [
    "instrumentl.com", #behind a paywall
    "grantwatch.com", #behind a paywall  
    "grantforward.com", #behind a paywall
    "grantgopher.com", #behind a paywall
    "grantmakers.io", #behind a paywall
    "grantselect.com", #behind a paywall
    "grantstation.com", #behind a paywall  
    "nerdwallet.com",
    "console.aws.amazon.com",
    "fundsforngos.org",
    "linkedin.com",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "google.com/search",
    "pinterest.com",
    "reddit.com",
    "tumblr.com",
    "medium.com/login",
    "wikipedia.org",
    "/login",
    "/signin",
    "/signup",
    "/register",
    "/cart",
    "/checkout",
    "/account",
    "/privacy",
    "/terms",
    "javascript:",
    "mailto:",
    "tel:",
    "whatsapp:",
]

# User agents for rotation (to avoid being blocked)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/109.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:108.0) Gecko/20100101 Firefox/108.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:108.0) Gecko/20100101 Firefox/108.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:108.0) Gecko/20100101 Firefox/108.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36 Edg/109.0.1518.55",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36 Edg/109.0.1518.55",
]

# Email notification settings
EMAIL_CONFIG = {
    "notification_email": os.getenv("NOTIFICATION_EMAIL", "team@opportunityhack.io"),
    "high_relevance_threshold": 0.65,  # Minimum score for high-relevance notification
    "report_style": "modern",         # modern or classic
    "include_charts": True,           # Include visual charts in email
    "max_grants_in_email": 25,        # Maximum number of grants to include in email
}

# Visual progress settings
VISUAL_CONFIG = {
    "use_rich_display": True,         # Use rich for display
    "show_progress_bars": True,       # Show progress bars
    "show_status_panel": True,        # Show status panel with stats
    "show_domain_progress": True,     # Show per-domain progress
    "update_interval": 0.5,           # Update interval in seconds
    "live_stats": True,               # Show live statistics
    "color_scheme": {
        "title": "bold blue",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "info": "cyan",
        "progress": "blue",
        "highlight": "magenta",
    }
}

# Domain-specific crawling configurations
# This allows fine-tuned control for specific websites that require special handling
DOMAIN_SPECIFIC_CONFIGS = {
    # Example for fundsforngos.org domains
    "fundsforngos.org": {
        "max_pages": 200,                # Maximum pages to crawl for this domain
        "depth_priority": True,          # Prioritize depth-first over breadth-first
        "max_depth": 4,                  # Maximum crawl depth for this domain
        "max_concurrent": 5,             # Maximum concurrent requests for this domain
        "respect_robots_txt": True,      # Override global robots.txt setting
        "delay_range": (1.5, 3.0),       # Custom delay range (slower)
        "content_patterns": [            # Content patterns to prioritize
            r"/grants/",                 # URLs containing /grants/
            r"/funds/",                  # URLs containing /funds/
            r"/opportunities/"           # URLs containing /opportunities/
        ],
        "url_blocklist": [               # Domain-specific URL patterns to block
            "/author/",                  # Skip author pages
            "/category/",                # Skip category listings
            "/tag/",                     # Skip tag listings
            "/page/",                    # Skip paginated archive pages
            "/search/"                   # Skip search result pages
        ],
        "content_filters": {             # Filters to apply to content
            "min_content_length": 1000,  # Minimum content length to consider
            "require_keywords": ["grant", "funding", "opportunity", "apply"],  # At least one required
        }
    },
    # Add more domain-specific configurations as needed
    "us.fundsforngos.org": {
        "max_pages": 150,
        "depth_priority": True,
        "max_depth": 4,
        "max_concurrent": 5,
        "delay_range": (1.5, 3.0),
        "content_patterns": ["/grants/", "/funds/", "/opportunities/"],
        "url_blocklist": ["/author/", "/category/", "/tag/", "/page/", "/search/"],
        "content_filters": {
            "min_content_length": 1000,
            "require_keywords": ["grant", "funding", "opportunity", "apply"],
        }
    },
    "fundsforcompanies.fundsforngos.org": {
        "max_pages": 150,
        "depth_priority": True,
        "max_depth": 4,
        "max_concurrent": 5,
        "delay_range": (1.5, 3.0),
        "content_patterns": ["/grants/", "/funds/", "/opportunities/"],
        "url_blocklist": ["/author/", "/category/", "/tag/", "/page/", "/search/"],
        "content_filters": {
            "min_content_length": 1000,
            "require_keywords": ["grant", "funding", "opportunity", "apply"],
        }
    }
}

# Google API settings and cost controls
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")

# Google API cost control settings
GOOGLE_API_CONFIG = {
    "max_queries_per_run": 100,              # Maximum number of search queries to execute per run (each costs money)
    "max_results_per_query": 10,           # Maximum number of results to fetch per query
    "google_cache_expiry": 604800,         # Google search results cache expiry time in seconds (1 week)
    "prioritize_queries": True,            # Prioritize queries based on relevance to current search
    "use_google_cache": True,              # Use cached results when available (even if expired)
    "monthly_budget_limit": 10,            # Maximum monthly budget for Google API calls (in USD)
    "enable_budget_tracking": False,       # Enable budget tracking (requires extra storage)
    "budget_tracking_file": str(DATA_DIR / "google_api_usage.json"),  # File to track API usage
}

# Claude API settings for grant writing
CLAUDE_API_CONFIG = {
    "api_key": os.getenv("CLAUDE_API_KEY", ""),  # Claude API key from environment
    "enabled": True,                            # Enable/disable Claude grant writing
    "model": "claude-3-5-sonnet-20240620",      # Claude model to use
    "max_tokens": 4000,                         # Maximum tokens for grant response
    "temperature": 0.3,                         # Lower temperature for more focused responses
    "auto_write_grants": True,                  # Auto-write grants for high relevance opportunities
    "max_grants_per_run": 5,                    # Maximum number of grants to write per run
    "grant_output_dir": str(OUTPUT_DIR / "auto_grants"),  # Directory to save auto-written grants
}

# Nonprofit organization profile for grant applications
NONPROFIT_PROFILE = {
    "name": "Opportunity Hack",
    "mission": "Empowering nonprofits through technology and connecting skilled volunteers to causes that matter.",
    "description": """Opportunity Hack is a 501(c)(3) nonprofit organization that connects technology volunteers with nonprofits to solve pressing social challenges. We host hackathons, organize skills-based volunteering, and build sustainable tech solutions for the nonprofit sector.""",
    "year_founded": 2013,
    "location": "Phoenix, Arizona",
    "website": "https://www.ohack.org",
    "impact_metrics": [
        "Helped 50+ nonprofits through technology innovation",
        "Engaged 1000+ volunteers in meaningful technology projects",
        "Developed 100+ technology solutions for the nonprofit sector",
        "Created $3M+ in value through pro-bono tech services"
    ],
    "focus_areas": [
        "Nonprofit technology capacity building",
        "Skills-based tech volunteering",
        "Social good hackathons",
        "Sustainable software development for nonprofits"
    ],
    "tech_capabilities": [
        "Web and mobile application development",
        "Data analytics and visualization",
        "CRM implementation and customization",
        "API integration and automation",
        "Cloud infrastructure and DevOps"
    ],
    "previous_funding": [
        "Arizona Community Foundation - $25,000 (2023)",
        "Microsoft Philanthropies - $50,000 (2022)",
        "PayPal Gives - $15,000 (2021)"
    ],
    "contact": {
        "name": "Program Director",
        "email": "team@opportunityhack.io",
        "phone": "(555) 123-4567"
    }
}

# Email server settings (for notifications)
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")