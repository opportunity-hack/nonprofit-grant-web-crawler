"""
Email utility functions for the Opportunity Hack Grant Finder.

This module provides functions for sending email notifications
about grant opportunities.
"""

import os
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any

from src.config import EMAIL_CONFIG, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD

# Configure logger
logger = logging.getLogger("email_utils")

def send_email_notification(grants: List, recipient: str) -> bool:
    """
    Send email notification with high-relevance grants.
    
    Args:
        grants: List of OpportunityHackGrant objects
        recipient: Email address to send notification to
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    # Filter for high-relevance grants
    high_relevance_threshold = EMAIL_CONFIG["high_relevance_threshold"]
    high_relevance_grants = [g for g in grants if g.relevance_score >= high_relevance_threshold]
    
    if not high_relevance_grants:
        logger.info("No high-relevance grants to notify about")
        return False
    
    try:
        # Email configuration
        smtp_server_addr = SMTP_SERVER or os.getenv("SMTP_SERVER", "")
        smtp_port_num = SMTP_PORT or int(os.getenv("SMTP_PORT", "587"))
        smtp_user_addr = SMTP_USER or os.getenv("SMTP_USER", "")
        smtp_password_text = SMTP_PASSWORD or os.getenv("SMTP_PASSWORD", "")
        
        if not all([smtp_server_addr, smtp_user_addr, smtp_password_text]):
            logger.warning("Email configuration incomplete. Skipping notification.")
            return False
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = smtp_user_addr
        msg['To'] = recipient
        msg['Subject'] = f"[Opportunity Hack] {len(high_relevance_grants)} New High-Relevance Grant Opportunities"
        
        # Select email style
        email_style = EMAIL_CONFIG.get("report_style", "modern")
        
        if email_style == "modern":
            body = _build_modern_email(high_relevance_grants)
        else:
            body = _build_classic_email(high_relevance_grants)
        
        # Attach HTML body
        msg.attach(MIMEText(body, 'html'))
        
        # Send email
        with smtplib.SMTP(smtp_server_addr, smtp_port_num) as server:
            server.starttls()
            server.login(smtp_user_addr, smtp_password_text)
            server.send_message(msg)
        
        logger.info(f"Email notification sent to {recipient}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")
        return False

def _build_modern_email(grants: List) -> str:
    """
    Build a modern-styled HTML email with grant opportunities.
    
    Args:
        grants: List of OpportunityHackGrant objects
        
    Returns:
        str: HTML content for the email
    """
    # Maximum grants to include in email
    max_grants = min(len(grants), EMAIL_CONFIG["max_grants_in_email"])
    
    # HTML header with styles
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                line-height: 1.6; 
                color: #333; 
                background-color: #f9f9f9;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #3366cc;
                color: white;
                padding: 20px;
                text-align: center;
                border-radius: 5px 5px 0 0;
            }}
            .grant {{ 
                margin-bottom: 30px;
                border-bottom: 1px solid #eee;
                padding: 20px;
                background-color: white;
                border-radius: 5px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            .title {{ 
                color: #3366cc; 
                font-size: 18px; 
                font-weight: bold;
                margin-bottom: 10px;
            }}
            .meta {{ 
                color: #666; 
                font-size: 14px; 
                margin: 5px 0;
                display: flex;
                flex-wrap: wrap;
            }}
            .meta-item {{
                margin-right: 20px;
                margin-bottom: 5px;
            }}
            .description {{ 
                margin: 15px 0;
                color: #444;
            }}
            .tag {{
                display: inline-block;
                background-color: #e6f3ff;
                color: #3366cc;
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 12px;
                margin-right: 5px;
                margin-bottom: 5px;
            }}
            .cta {{ 
                margin-top: 15px;
            }}
            .button {{
                display: inline-block;
                background-color: #4CAF50;
                color: white;
                padding: 8px 15px;
                text-decoration: none;
                border-radius: 4px;
                margin-right: 10px;
                margin-bottom: 10px;
                font-weight: bold;
            }}
            .button.secondary {{
                background-color: #3366cc;
            }}
            .footer {{
                text-align: center;
                padding: 20px;
                color: #666;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Opportunity Hack Grant Finder</h1>
                <p>We've found {len(grants)} new high-relevance grant opportunities that might interest you</p>
            </div>
    """
    
    # Add grants to email body
    for grant in grants[:max_grants]:
        funding_str = str(grant.funding_amount) if grant.funding_amount else "Amount not specified"
        deadline_str = f"{grant.deadline}" if grant.deadline else "Not specified"
        
        # Create tech focus tags
        tech_tags = ""
        if grant.tech_focus:
            for tech in grant.tech_focus[:5]:  # Limit to 5 tags
                tech_tags += f'<span class="tag">{tech}</span>'
        else:
            tech_tags = '<span class="tag">Not specified</span>'
        
        html += f"""
        <div class="grant">
            <div class="title">{grant.title}</div>
            <div class="meta">
                <div class="meta-item"><strong>Source:</strong> {grant.source_name}</div>
                <div class="meta-item"><strong>Deadline:</strong> {deadline_str}</div>
                <div class="meta-item"><strong>Funding:</strong> {funding_str}</div>
            </div>
            <div class="description">
                {grant.description[:300]}{'...' if len(grant.description) > 300 else ''}
            </div>
            <div>
                <strong>Tech Focus:</strong><br>
                {tech_tags}
            </div>
            <div class="cta">
                <a href="{grant.source_url}" class="button secondary">View Details</a>
                {f'<a href="{grant.application_url}" class="button">Apply Now</a>' if grant.application_url else ''}
            </div>
        </div>
        """
    
    # If there are more grants than we're showing
    if len(grants) > max_grants:
        html += f"""
        <p style="text-align: center; margin: 20px 0;">
            <em>Plus {len(grants) - max_grants} more grant opportunities...</em>
        </p>
        """
    
    # Footer
    html += """
            <div class="footer">
                <p>This notification was automatically sent by the Opportunity Hack Grant Finder.</p>
                <p>Generated on: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

def _build_classic_email(grants: List) -> str:
    """
    Build a classic-styled HTML email with grant opportunities.
    
    Args:
        grants: List of OpportunityHackGrant objects
        
    Returns:
        str: HTML content for the email
    """
    # Maximum grants to include in email
    max_grants = min(len(grants), EMAIL_CONFIG["max_grants_in_email"])
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .grant {{ margin-bottom: 30px; border-bottom: 1px solid #ccc; padding-bottom: 20px; }}
            .title {{ color: #3366cc; font-size: 18px; font-weight: bold; }}
            .meta {{ color: #666; font-size: 14px; margin: 5px 0; }}
            .description {{ margin-top: 10px; }}
            .cta {{ margin-top: 15px; }}
            .cta a {{ background-color: #4CAF50; color: white; padding: 8px 15px; text-decoration: none; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <h1>Opportunity Hack Grant Finder Results</h1>
        <p>We've found {len(grants)} new high-relevance grant opportunities that might interest you:</p>
    """
    
    # Add grants to email body
    for grant in grants[:max_grants]:
        funding_str = str(grant.funding_amount) if grant.funding_amount else "Amount not specified"
        deadline_str = f"Deadline: {grant.deadline}" if grant.deadline else "Deadline not specified"
        tech_focus_str = ', '.join(grant.tech_focus) if grant.tech_focus else "Not specified"
        
        html += f"""
        <div class="grant">
            <div class="title">{grant.title}</div>
            <div class="meta">
                <strong>Source:</strong> {grant.source_name} | 
                <strong>{deadline_str}</strong> | 
                <strong>{funding_str}</strong>
            </div>
            <div class="meta">
                <strong>Tech Focus:</strong> {tech_focus_str}
            </div>
            <div class="description">
                {grant.description[:300]}{'...' if len(grant.description) > 300 else ''}
            </div>
            <div class="cta">
                <a href="{grant.source_url}">View Details</a>
                {f'<a href="{grant.application_url}" style="margin-left: 10px;">Apply Now</a>' if grant.application_url else ''}
            </div>
        </div>
        """
    
    html += """
        <p>This notification was automatically sent by the Opportunity Hack Grant Finder.</p>
    </body>
    </html>
    """
    
    return html