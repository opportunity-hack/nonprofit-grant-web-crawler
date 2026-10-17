"""Hand-verified recurring programs.

Small on purpose. Every entry was checked against the funder's official
page on the verified_at date, and the entry says exactly what state the
program is in (open / rolling / invitation-only / annual cycle closed).
When a weekly refresh runs, these entries keep their verified_at so the
page can show how fresh the human check is; re-verify before changing
any status text.
"""

from __future__ import annotations

from datetime import date
from typing import List

from ..models import FundingAmount, GrantRecord

VERIFIED = "2026-10-16"


def collect(today: date | None = None) -> List[GrantRecord]:
    today = today or date.today()
    base = dict(found_date=today.isoformat(), source_api="curated", verified_at=VERIFIED)
    return [
        GrantRecord(
            title="Google Ad Grants",
            description=(
                "Up to $10,000 per month in free Google Search advertising credit for eligible "
                "nonprofits, through Google for Nonprofits. Rolling applications, no deadline. "
                "Governmental entities, hospitals, and schools are not eligible."
            ),
            source_url="https://www.google.com/grants/",
            source_name="Google Ad Grants",
            application_url="https://www.google.com/grants/",
            deadline=None,
            eligibility="Registered 501(c)(3) nonprofits with a quality website; must enroll in Google for Nonprofits.",
            funding_amount=FundingAmount(amount=10000, range_max=None),
            tech_focus=["marketing", "technology"],
            relevance_score=1.0,
            source_id="curated-google-ad-grants",
            **base,
        ),
        GrantRecord(
            title="AWS Imagine Grant",
            description=(
                "Annual AWS grant for nonprofits using cloud technology and AI for social good: "
                "up to $200,000 in unrestricted funding plus up to $100,000 in AWS credits, "
                "depending on category. The 2026 cycle is closed; the next cycle is expected to "
                "open in spring 2027. Sign up on the program page for alerts."
            ),
            source_url="https://aws.amazon.com/government-education/nonprofits/aws-imagine-grant-program/",
            source_name="AWS (Amazon Web Services)",
            application_url="https://aws.amazon.com/government-education/nonprofits/aws-imagine-grant-program/",
            deadline=None,
            eligibility="Nonprofits with registered 501(c) status based in the US; educational institutions excluded.",
            funding_amount=FundingAmount(amount=200000),
            tech_focus=["cloud", "artificial intelligence", "technology"],
            relevance_score=1.0,
            source_id="curated-aws-imagine-grant",
            **base,
        ),
        GrantRecord(
            title="Okta for Good product donation",
            description=(
                "Eligible nonprofits receive 50 free Okta Workforce Identity licenses and 50% off "
                "additional licenses and Auth0 plans, plus free training. Rolling; apply through "
                "Okta for Good or TechSoup."
            ),
            source_url="https://www.okta.com/oktaforgood/",
            source_name="Okta for Good",
            application_url="https://www.okta.com/oktaforgood/",
            deadline=None,
            eligibility="Validated 501(c)(3) nonprofits (verified via Goodstack); hospitals, healthcare, schools, and government entities ineligible.",
            tech_focus=["cybersecurity", "identity", "technology"],
            relevance_score=0.9,
            source_id="curated-okta-for-good",
            **base,
        ),
        GrantRecord(
            title="Twilio.org Impact Fund and Impact Access Program",
            description=(
                "Twilio.org funds nonprofit tech projects in digital transformation, humanitarian "
                "assistance, and climate action. Impact Fund grant rounds are currently "
                "invitation-only; the Impact Access Program is open and provides product credits "
                "and discounts to eligible nonprofits."
            ),
            source_url="https://www.twilio.org/en-us/support-and-resources/impact-fund",
            source_name="Twilio.org",
            application_url="https://www.twilio.org/en-us/support-and-resources/impact-fund",
            deadline=None,
            eligibility="Public benefit nonprofits (501(c)(3) and equivalents); government and political organizations ineligible.",
            tech_focus=["communications", "technology"],
            relevance_score=0.9,
            source_id="curated-twilio-org",
            **base,
        ),
        GrantRecord(
            title="TechSoup donated and discounted software",
            description=(
                "TechSoup is the main directory of donated and discounted software and hardware "
                "for nonprofits (Microsoft, Adobe, Okta, and hundreds more). Registering your "
                "organization is free and also validates your nonprofit status for many other "
                "programs, including Google for Nonprofits."
            ),
            source_url="https://www.techsoup.org/",
            source_name="TechSoup",
            application_url="https://www.techsoup.org/",
            deadline=None,
            eligibility="Registered 501(c)(3) nonprofits and public libraries.",
            tech_focus=["software", "technology"],
            relevance_score=0.9,
            source_id="curated-techsoup",
            **base,
        ),
    ]
