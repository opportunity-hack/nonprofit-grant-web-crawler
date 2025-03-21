# Opportunity Hack Grant Finder

A specialized web crawler designed to find grant opportunities relevant to Opportunity Hack's mission of technology for social good.

## Features

- Crawls targeted grant provider websites, foundation pages, and tech-for-good sources
- Integrates with Google Custom Search API for extended search capabilities
- Monitors RSS feeds for new grant announcements
- Extracts key information:
  - Funding amounts
  - Deadlines
  - Tech focus areas
  - Nonprofit sectors
  - Eligibility requirements
- Calculates relevance scores for each opportunity
- Generates CSV, JSON, and HTML reports
- Sends email notifications for high-relevance grants

## Project Structure

```
opportunity-hack-grant-finder/
├── src/                                # Source code
│   ├── __init__.py
│   ├── config.py                       # Configuration settings
│   ├── opportunity_hack_grant_finder.py # Main implementation
│   └── utils/                          # Utility modules
│       ├── __init__.py
│       ├── analyzer.py                 # Grant opportunity analysis
│       ├── crawler.py                  # Advanced web crawler implementation
│       ├── email_utils.py              # Email notification utilities
│       ├── grant_writer.py             # Claude-powered grant application writer
│       ├── parsing.py                  # HTML parsing utilities
│       └── reporting.py                # Report generation utilities
│
├── data/                               # Data directory
│   ├── opportunity_hack/               # Opportunity Hack specific data
│   │   └── auto_grants/                # Auto-generated grant applications
│   └── cache/                          # Cached web pages
│
├── logs/                               # Log files
│
├── scripts/                            # Scripts directory
│   ├── run_grant_finder.py             # Main script to run the crawler
│   └── schedule_crawler.py             # Script for scheduling regular runs
│
├── tests/                              # Tests directory
│   ├── __init__.py
│   ├── test_crawler.py
│   ├── test_parsing.py
│   └── test_reporting.py
│
├── .env.example                        # Example environment variables
├── .gitignore                          # Git ignore file
├── LICENSE                             # License file
├── proxies.txt                         # Proxy list (optional)
├── README.md                           # This readme file
└── requirements.txt                    # Python dependencies
```

## Installation

### MacOS/Linux
1. Clone the repository
```bash
git clone https://github.com/opportunity-hack/grant-finder.git
cd opportunity-hack-grant-finder
```

2. Create a virtual environment (tested with Python 3.9)
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Create required directories
```bash
mkdir -p data/raw data/processed data/reports logs
```

5. Set up environment variables
```bash
cp .env.example .env
# Edit .env with your settings
```

### Windows
1. Clone the repository
```bash
git clone https://github.com/opportunity-hack/grant-finder.git
cd opportunity-hack-grant-finder
```

2. Create a virtual environment (tested with Python 3.9)
```bash
python -m venv venv
venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Create required directories
```bash
mkdir "data/raw" "data/processed" "data/reports" "logs"
```

5. Set up environment variables
```bash
cp .env.example .env
# Edit .env with your settings
```

Required environment variables:
```
# Google Custom Search (optional but recommended)
GOOGLE_API_KEY=your_google_api_key https://console.cloud.google.com/apis/credentials?referrer=search
GOOGLE_CSE_ID=your_google_cse_id https://programmablesearchengine.google.com/controlpanel/create
CLAUDE_API_KEY=your_claude_api_key https://console.anthropic.com/settings/keys

# Email notifications (optional)
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASSWORD=your_password
NOTIFICATION_EMAIL=team@opportunityhack.io
```

## Usage

1. Basic usage:
```bash
python main.py
```

2. With options:
```bash
# Disable email notifications
python main.py --no-email

# Disable Google Search
python main.py --no-google

# Configure crawl depth and concurrency
python main.py --max-depth 3 --concurrent 10 --delay 1.0

# Specify custom output directory
python main.py --output-dir ./data/custom

# Memory efficiency with incremental saving
python main.py --save-interval 20  # Save every 20 grants found
python main.py --no-incremental-save  # Only save at the end
```

3. Domain-specific crawling configuration:
```bash
# Set specific crawling parameters for a domain
python main.py --domain fundsforngos.org --domain-max-pages 200 --domain-max-depth 4 --domain-depth-first

# Control rate limiting for intensive sites
python main.py --domain fundsforngos.org --domain-delay 1.5 3.0 --domain-max-concurrent 2

# Filter content patterns
python main.py --domain fundsforngos.org \
  --domain-content-pattern "/grants/" \
  --domain-content-pattern "/funds/" \
  --domain-content-pattern "/opportunities/" \
  --domain-block-pattern "/author/" \
  --domain-block-pattern "/category/" \
  --domain-block-pattern "/tag/"
```

4. Use proxies (optional):
Create a file named `proxies.txt` with one proxy per line:
```
http://proxy1.example.com:8080
http://proxy2.example.com:8080
```

## Output Files

The crawler generates several output files in the `data` directory:

1. `data/processed/opportunity_hack_grants_TIMESTAMP.json` - Complete grant data in JSON format
2. `data/processed/opportunity_hack_grants_TIMESTAMP.csv` - Grant data in CSV format for spreadsheet analysis
3. `data/reports/summary_report_TIMESTAMP.html` - Visual HTML report with charts and statistics

## Configuration

You can customize the crawler behavior by editing `src/config.py`:

- Keywords for relevance scoring
- Technology skill categories
- Nonprofit sectors
- Crawling parameters
- Relevance thresholds

### Domain-Specific Crawling Configuration

For sites with thousands of pages that might overwhelm the crawler, you can define domain-specific crawling configurations in `src/config.py`:

```python
# Domain-specific crawling configurations
DOMAIN_SPECIFIC_CONFIGS = {
    "fundsforngos.org": {
        "max_pages": 200,                # Maximum pages to crawl for this domain
        "depth_priority": True,          # Prioritize depth-first over breadth-first
        "max_depth": 4,                  # Maximum crawl depth for this domain
        "max_concurrent": 2,             # Maximum concurrent requests for this domain
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
    }
}
```

You can also specify these configurations at runtime using command-line arguments (see Usage section).

## Development

1. Run tests:
```bash
pytest
```

2. Add custom grant sources:
   - Edit `src/config.py` and add URLs to the `TARGET_URLS` list
   - Customize search queries in the `SEARCH_QUERIES` list

3. Customize grant detection:
   - Edit keyword lists in `src/config.py`
   - Modify parsing rules in `src/utils/parsing.py`

## Running on a Schedule

To run the grant finder automatically on a schedule, you can use the provided script:

```bash
python scripts/schedule_crawler.py --interval daily
```

Or set up a cron job (Linux/Mac) or Task Scheduler (Windows):

Example cron job (runs daily at 8 AM):
```
0 8 * * * cd /path/to/opportunity-hack-grant-finder && /path/to/venv/bin/python scripts/run_grant_finder.py >> logs/cron.log 2>&1
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request