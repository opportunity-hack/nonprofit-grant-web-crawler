"""
Reporting utility functions for the Opportunity Hack Grant Finder.

This module provides functions for generating summary reports
about grant opportunities.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from src.config import OUTPUT_DIR

# Configure logger
logger = logging.getLogger("reporting")

def generate_summary_report(grants: List, output_dir: Path = OUTPUT_DIR) -> Path:
    """
    Generate a summary report of the grant findings.
    
    Args:
        grants: List of OpportunityHackGrant objects
        output_dir: Directory to save the report
        
    Returns:
        Path: Path to the generated report file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"summary_report_{timestamp}.html"
    
    try:
        # Count grants by tech focus
        tech_focus_counts = {}
        for grant in grants:
            for tech in grant.tech_focus:
                tech_focus_counts[tech] = tech_focus_counts.get(tech, 0) + 1
        
        # Count grants by nonprofit sector
        sector_counts = {}
        for grant in grants:
            for sector in grant.nonprofit_sector:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
        
        # Sort by count (descending)
        tech_focus_sorted = sorted(tech_focus_counts.items(), key=lambda x: x[1], reverse=True)
        sector_sorted = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
        
        # Calculate average funding amount
        funding_amounts = [grant.funding_amount.amount for grant in grants if grant.funding_amount]
        avg_funding = sum(funding_amounts) / len(funding_amounts) if funding_amounts else 0
        
        # Generate HTML report
        html = _generate_html_report(grants, tech_focus_sorted, sector_sorted, avg_funding)
        
        # Create directory if it doesn't exist
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write report to file
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Generate JSON data for potential visualization
        json_data = _generate_json_data(grants, tech_focus_sorted, sector_sorted, avg_funding)
        json_path = output_dir / f"report_data_{timestamp}.json"
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)
        
        logger.info(f"Summary report generated: {report_path}")
        logger.info(f"Report data saved to: {json_path}")
        
        return report_path
    
    except Exception as e:
        logger.error(f"Error generating summary report: {str(e)}")
        # Create a minimal error report
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"""
            <html>
            <head><title>Error Report</title></head>
            <body>
                <h1>Error Generating Report</h1>
                <p>An error occurred while generating the report: {str(e)}</p>
                <p>Found {len(grants)} grants but could not process them fully.</p>
            </body>
            </html>
            """)
        return report_path

def _generate_html_report(grants, tech_focus_sorted, sector_sorted, avg_funding):
    """Generate the HTML report content."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Opportunity Hack Grant Finder Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }}
            h1, h2, h3 {{ color: #333; }}
            .summary {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
            .summary-box {{ background: #f5f5f5; padding: 20px; border-radius: 8px; width: 30%; text-align: center; }}
            .summary-number {{ font-size: 36px; font-weight: bold; color: #3366cc; }}
            .summary-label {{ font-size: 16px; color: #666; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .chart {{ margin: 30px 0; }}
            .bar {{ height: 30px; background-color: #3366cc; margin-bottom: 10px; }}
            .bar-label {{ display: inline-block; width: 200px; }}
        </style>
    </head>
    <body>
        <h1>Opportunity Hack Grant Finder Summary Report</h1>
        <p>Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <div class="summary">
            <div class="summary-box">
                <div class="summary-number">{len(grants)}</div>
                <div class="summary-label">Total Grants Found</div>
            </div>
            <div class="summary-box">
                <div class="summary-number">${avg_funding:,.2f}</div>
                <div class="summary-label">Average Funding Amount</div>
            </div>
            <div class="summary-box">
                <div class="summary-number">{sum(1 for g in grants if g.volunteer_component)}</div>
                <div class="summary-label">Volunteer Opportunities</div>
            </div>
        </div>
        
        <h2>Top Technology Focus Areas</h2>
        <div class="chart">
    """
    
    # Add tech focus chart
    max_tech_count = tech_focus_sorted[0][1] if tech_focus_sorted else 0
    for tech, count in tech_focus_sorted[:10]:  # Top 10
        percentage = (count / max_tech_count) * 100 if max_tech_count > 0 else 0
        html += f"""
            <div>
                <span class="bar-label">{tech}</span>
                <div class="bar" style="width: {percentage}%; display: inline-block;"></div>
                <span>{count}</span>
            </div>
        """
    
    html += """
        </div>
        
        <h2>Top Nonprofit Sectors</h2>
        <div class="chart">
    """
    
    # Add nonprofit sector chart
    max_sector_count = sector_sorted[0][1] if sector_sorted else 0
    for sector, count in sector_sorted[:10]:  # Top 10
        percentage = (count / max_sector_count) * 100 if max_sector_count > 0 else 0
        html += f"""
            <div>
                <span class="bar-label">{sector}</span>
                <div class="bar" style="width: {percentage}%; display: inline-block;"></div>
                <span>{count}</span>
            </div>
        """
    
    html += """
        </div>
        
        <h2>Grant Opportunities</h2>
        <table>
            <tr>
                <th>Title</th>
                <th>Source</th>
                <th>Deadline</th>
                <th>Funding</th>
                <th>Relevance Score</th>
            </tr>
    """
    
    # Add grant rows
    for grant in grants:
        funding_str = str(grant.funding_amount) if grant.funding_amount else "Not specified"
        deadline_str = grant.deadline if grant.deadline else "Not specified"
        
        html += f"""
            <tr>
                <td><a href="{grant.source_url}">{grant.title}</a></td>
                <td>{grant.source_name}</td>
                <td>{deadline_str}</td>
                <td>{funding_str}</td>
                <td>{grant.relevance_score:.2f}</td>
            </tr>
        """
    
    html += """
        </table>
        <script>
            // Add potential for interactive visualizations in the future
            console.log("Report generated successfully");
        </script>
    </body>
    </html>
    """
    
    return html

def _generate_json_data(grants, tech_focus_sorted, sector_sorted, avg_funding):
    """Generate JSON data for potential visualization."""
    return {
        "summary": {
            "total_grants": len(grants),
            "average_funding": avg_funding,
            "volunteer_opportunities": sum(1 for g in grants if g.volunteer_component),
            "remote_participation": sum(1 for g in grants if g.remote_participation),
            "hackathon_eligible": sum(1 for g in grants if g.hackathon_eligible),
            "timestamp": datetime.now().isoformat()
        },
        "tech_focus": {tech: count for tech, count in tech_focus_sorted},
        "nonprofit_sectors": {sector: count for sector, count in sector_sorted},
        "grants_by_relevance": [
            {
                "title": grant.title,
                "source": grant.source_name,
                "url": grant.source_url,
                "relevance_score": grant.relevance_score
            }
            for grant in sorted(grants, key=lambda x: x.relevance_score, reverse=True)
        ]
    }