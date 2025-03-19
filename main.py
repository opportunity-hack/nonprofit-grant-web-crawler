#!/usr/bin/env python
"""
Opportunity Hack Grant Finder - Run Script

Usage:
    python run_grant_finder.py [--no-email] [--no-google] [--no-rss]
"""

import asyncio
import argparse
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# Import the grant finder and utilities
from src.opportunity_hack_grant_finder import OpportunityHackGrantFinder, logger
from src.utils.email_utils import send_email_notification
from src.utils.reporting import generate_summary_report
import src.config as config
from src.config import RELEVANCE_CONFIG, CLAUDE_API_CONFIG

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Opportunity Hack Grant Finder")
    
    parser.add_argument(
        "--no-email", 
        action="store_true", 
        help="Disable email notifications"
    )
    
    parser.add_argument(
        "--no-google", 
        action="store_true", 
        help="Disable Google Custom Search"
    )
    
    parser.add_argument(
        "--no-rss", 
        action="store_true", 
        help="Disable RSS feed fetching"
    )
    
    parser.add_argument(
        "--max-depth", 
        type=int, 
        default=config.CRAWLER_CONFIG["max_depth"],
        help="Maximum crawl depth"
    )
    
    parser.add_argument(
        "--concurrent", 
        type=int, 
        default=config.CRAWLER_CONFIG["max_concurrent_requests"],
        help="Maximum concurrent requests"
    )
    
    parser.add_argument(
        "--delay", 
        type=float, 
        default=config.CRAWLER_CONFIG["rate_limit_delay"],
        help="Delay between requests in seconds"
    )
    
    parser.add_argument(
        "--output-dir", 
        type=str, 
        default=str(config.OUTPUT_DIR),
        help="Output directory for results"
    )
    
    parser.add_argument(
        "--proxy-file", 
        type=str, 
        default="proxies.txt",
        help="File containing proxy servers (one per line)"
    )
    
    # Cost control options
    parser.add_argument(
        "--max-google-queries",
        type=int,
        default=config.GOOGLE_API_CONFIG["max_queries_per_run"],
        help="Maximum number of Google search queries to run (cost control)"
    )
    
    parser.add_argument(
        "--google-cache",
        action="store_true",
        help="Force use of Google search cache even if expired"
    )
    
    parser.add_argument(
        "--crawl-root-on-404",
        action="store_true",
        default=config.CRAWLER_CONFIG["crawl_root_on_404"],
        help="Try to crawl the root domain when encountering 404 errors"
    )
    
    # Auto grant writing options
    parser.add_argument(
        "--no-auto-grants",
        action="store_true",
        help="Disable automatic grant writing with Claude API"
    )
    
    parser.add_argument(
        "--auto-grant-threshold",
        type=float,
        default=RELEVANCE_CONFIG["auto_grant_threshold"],
        help=f"Minimum relevance score threshold for auto-grant writing (default: {RELEVANCE_CONFIG['auto_grant_threshold']})"
    )
    
    parser.add_argument(
        "--max-grants",
        type=int,
        default=CLAUDE_API_CONFIG["max_grants_per_run"],
        help=f"Maximum number of grants to write per run (default: {CLAUDE_API_CONFIG['max_grants_per_run']})"
    )
    
    # Domain-specific configuration arguments
    parser.add_argument(
        "--domain",
        type=str,
        help="Domain to apply specific configuration to (e.g. fundsforngos.org)"
    )
    
    parser.add_argument(
        "--domain-max-pages",
        type=int,
        help="Maximum pages to crawl for the specified domain"
    )
    
    parser.add_argument(
        "--domain-max-depth",
        type=int,
        help="Maximum crawl depth for the specified domain"
    )
    
    parser.add_argument(
        "--domain-depth-first",
        action="store_true",
        help="Use depth-first crawling strategy for the specified domain"
    )
    
    parser.add_argument(
        "--domain-max-concurrent",
        type=int,
        help="Maximum concurrent requests for the specified domain"
    )
    
    parser.add_argument(
        "--domain-delay",
        type=float,
        nargs=2,
        metavar=("MIN", "MAX"),
        help="Custom delay range (min max) for the specified domain"
    )
    
    parser.add_argument(
        "--domain-content-pattern",
        type=str,
        action="append",
        help="Content patterns to prioritize for the specified domain (can be used multiple times)"
    )
    
    parser.add_argument(
        "--domain-block-pattern",
        type=str,
        action="append",
        help="URL patterns to block for the specified domain (can be used multiple times)"
    )
    
    # Incremental saving options
    parser.add_argument(
        "--no-incremental-save",
        action="store_true",
        help="Disable incremental saving (only save at the end)"
    )
    
    parser.add_argument(
        "--save-interval",
        type=int,
        default=config.CRAWLER_CONFIG["save_interval"],
        help="Number of grants to discover before saving (0 = only at end)"
    )
    
    return parser.parse_args()

async def main():
    """Main entry point for the application."""
    # Parse arguments
    args = parse_arguments()
    
    # Setup console
    console = Console()
    console.print("[bold blue]Opportunity Hack Grant Finder[/bold blue]")
    console.print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    console.print("Searching for tech-for-good grant opportunities...")
    
    # Load proxy list if available
    proxy_list = []
    proxy_path = Path(args.proxy_file)
    if proxy_path.exists():
        with open(proxy_path, 'r') as f:
            proxy_list = [line.strip() for line in f if line.strip()]
        console.print(f"[green]Loaded {len(proxy_list)} proxies[/green]")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Update config settings based on command line arguments
    config.GOOGLE_API_CONFIG["max_queries_per_run"] = args.max_google_queries
    if args.google_cache:
        config.GOOGLE_API_CONFIG["use_google_cache"] = True
    config.CRAWLER_CONFIG["crawl_root_on_404"] = args.crawl_root_on_404
    
    # Apply domain-specific configurations from command line
    if args.domain:
        domain_config = {}
        
        # Create or update domain config
        if args.domain in config.DOMAIN_SPECIFIC_CONFIGS:
            # Update existing config
            domain_config = config.DOMAIN_SPECIFIC_CONFIGS[args.domain].copy()
        
        # Apply command-line overrides
        if args.domain_max_pages:
            domain_config["max_pages"] = args.domain_max_pages
        
        if args.domain_max_depth:
            domain_config["max_depth"] = args.domain_max_depth
        
        if args.domain_depth_first:
            domain_config["depth_priority"] = True
        
        if args.domain_max_concurrent:
            domain_config["max_concurrent"] = args.domain_max_concurrent
        
        if args.domain_delay:
            domain_config["delay_range"] = (args.domain_delay[0], args.domain_delay[1])
        
        if args.domain_content_pattern:
            domain_config["content_patterns"] = args.domain_content_pattern
        
        if args.domain_block_pattern:
            domain_config["url_blocklist"] = args.domain_block_pattern
        
        # Set or update the domain-specific configuration
        config.DOMAIN_SPECIFIC_CONFIGS[args.domain] = domain_config
        
        console.print(f"[green]Applied custom crawling configuration for domain: {args.domain}[/green]")
        for key, value in domain_config.items():
            console.print(f"  - {key}: {value}")
    
    # Create and run finder
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Crawling grant sources...", total=None)
        
        # If command-line arguments were provided to override cost controls
        if args.max_google_queries or args.google_cache:
            console.print(f"[yellow]Cost controls applied: Max Google queries={args.max_google_queries}, Use cache={args.google_cache}[/yellow]")
            
        # Display incremental saving settings
        if not args.no_incremental_save:
            console.print(f"[green]Incremental saving enabled: Saving every {args.save_interval} grants[/green]")
        else:
            console.print("[yellow]Incremental saving disabled: Results will only be saved at the end[/yellow]")

        # Print all parameters for use_google_search
        use_google = not args.no_google and bool(config.GOOGLE_API_KEY and config.GOOGLE_CSE_ID)
        console.print(f"[blue]Using Google search: {use_google}[/blue]")
        
        # For security, don't print the actual API key values
        console.print(f"no_google: {args.no_google}, GOOGLE_API_KEY: {'configured' if config.GOOGLE_API_KEY else 'missing'}, GOOGLE_CSE_ID: {'configured' if config.GOOGLE_CSE_ID else 'missing'}")
        
        # Add warning about Google API usage
        if use_google:
            console.print("[yellow]NOTE: If Google search fails with 'Request contains an invalid argument', the program will use static seed URLs instead[/yellow]")
            console.print("[yellow]To avoid these errors completely, you can use --no-google flag[/yellow]")
            
        # Set up auto-grant writing configuration
        auto_grants_enabled = CLAUDE_API_CONFIG["enabled"] and not args.no_auto_grants and CLAUDE_API_CONFIG["api_key"]
        console.print(f"[blue]Auto grant writing: {auto_grants_enabled}[/blue]")
        
        # Update configuration based on command line arguments
        if args.no_auto_grants:
            CLAUDE_API_CONFIG["auto_write_grants"] = False
        
        if args.auto_grant_threshold != RELEVANCE_CONFIG["auto_grant_threshold"]:
            RELEVANCE_CONFIG["auto_grant_threshold"] = args.auto_grant_threshold
            console.print(f"[green]Auto grant threshold set to: {args.auto_grant_threshold}[/green]")
            
        if args.max_grants != CLAUDE_API_CONFIG["max_grants_per_run"]:
            CLAUDE_API_CONFIG["max_grants_per_run"] = args.max_grants
            console.print(f"[green]Maximum grants per run set to: {args.max_grants}[/green]")
            
        # Display Claude API status
        if auto_grants_enabled:
            console.print(f"[green]Claude API configured: Will auto-write grants with relevance score ≥ {RELEVANCE_CONFIG['auto_grant_threshold']}[/green]")
            console.print(f"[green]Auto-written grants will be saved to: {CLAUDE_API_CONFIG['grant_output_dir']}[/green]")
        elif CLAUDE_API_CONFIG["api_key"] and args.no_auto_grants:
            console.print("[yellow]Auto grant writing disabled with --no-auto-grants flag[/yellow]")
        elif not CLAUDE_API_CONFIG["api_key"]:
            console.print("[yellow]Claude API key not configured, auto grant writing disabled[/yellow]")
            console.print("[yellow]Set CLAUDE_API_KEY environment variable to enable this feature[/yellow]")
        
        finder = OpportunityHackGrantFinder(
            max_concurrent_requests=args.concurrent,
            rate_limit_delay=args.delay,
            max_depth=args.max_depth,
            proxy_list=proxy_list,
            use_google_search=not args.no_google and bool(config.GOOGLE_API_KEY and config.GOOGLE_CSE_ID),
            use_rss_feeds=not args.no_rss,
            incremental_save=not args.no_incremental_save,
            save_interval=args.save_interval,
            output_dir=output_dir
        )
        
        grants = await finder.run()
        progress.update(task, completed=True)
    
    # Save results
    if grants:
        json_path, csv_path = finder.save_results(output_dir)
        console.print(f"[green]Found {len(grants)} grant opportunities![/green]")
        console.print(f"Results saved to: {json_path}")
        console.print(f"CSV exported to: {csv_path}")
        
        # Generate summary report
        report_path = generate_summary_report(grants, output_dir)
        console.print(f"Summary report: {report_path}")
        
        # Send email notification if configured and not disabled
        if not args.no_email and config.EMAIL_CONFIG["notification_email"]:
            if send_email_notification(grants, config.EMAIL_CONFIG["notification_email"]):
                console.print(f"[green]Email notification sent to {config.EMAIL_CONFIG['notification_email']}[/green]")
    else:
        console.print("[yellow]No grant opportunities found[/yellow]")
    
    console.print(f"[bold green]Grant finding completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold green]")

if __name__ == "__main__":
    try:
        # Check for required packages
        try:
            import aiohttp
            import feedparser
            import bs4
            from googleapiclient.discovery import build
            import pandas as pd
            from rich.console import Console
        except ImportError as e:
            module_name = str(e).split("'")[1]
            print(f"\nError: Missing required package: {module_name}")
            print("Please install the required packages using:")
            print("pip install -r requirements.txt")
            sys.exit(1)
            
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Grant finder interrupted by user")
        print("\nGrant finder interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        print(f"\nError: {str(e)}")
        sys.exit(1)