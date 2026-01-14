"""
Job Intelligence module for finding and analyzing career opportunities.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from spider_nix.crawler import SpiderNix, CrawlResult
from spider_nix.osint.analyzer import ContentAnalyzer, AnalysisResult
from spider_nix.osint.reconnaissance import SubdomainEnumerator, SubdomainResult

logger = logging.getLogger(__name__)


@dataclass
class JobOpportunity:
    """Detected job opportunity."""
    
    company: str
    url: str
    title: str | None = None
    seniority: str | None = None  # Junior, Senior, Staff, etc.
    remote_policy: str | None = None  # Remote, Hybrid, On-site
    salary_range: str | None = None
    tech_stack: list[str] = field(default_factory=list)
    score: float = 0.0
    timestamp: str | None = None


class CareerPageFinder:
    """Find career pages using subdomain discovery and common paths."""

    CAREER_SUBDOMAINS = [
        "careers", "jobs", "join", "work", "talent", "people", "hr", "recruiting"
    ]

    CAREER_PATHS = [
        "/careers", "/jobs", "/join-us", "/work-with-us", "/about/careers"
    ]

    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.enumerator = SubdomainEnumerator(max_concurrent=max_concurrent)

    async def find(self, domain: str) -> list[str]:
        """
        Find career page URLs for a domain.
        
        Returns:
            List of discovered career page URLs
        """
        urls = set()
        
        # 1. Check subdomains (careers.company.com)
        logger.info(f"Checking career subdomains for {domain}...")
        subdomains = await self.enumerator.enumerate(
            domain, 
            use_crt=True, 
            use_bruteforce=True, 
            wordlist=self.CAREER_SUBDOMAINS
        )
        
        for sub in subdomains:
            if sub.alive:
                for protocol in ["https", "http"]:
                    urls.add(f"{protocol}://{sub.subdomain}")

        # 2. Check common paths on main domain
        logger.info(f"Checking common career paths for {domain}...")
        base_urls = [f"https://{domain}", f"https://www.{domain}"]
        spider = SpiderNix() # Use spider for efficient checking
        
        for base in base_urls:
            for path in self.CAREER_PATHS:
                url = f"{base}{path}"
                try:
                    # Quick head request check would be better, but spider.crawl works
                    # We'll use a simplified check here or rely on the spider's full crawl later
                    # For now, let's just add them as candidates if the base domain is alive
                    urls.add(url)
                except Exception:
                    pass

        return list(urls)


class JobAnalyzer(ContentAnalyzer):
    """Analyze content for job-related signals."""

    SENIORITY_KEYWORDS = {
        "Staff": 10,
        "Principal": 10,
        "Lead": 8,
        "Senior": 5,
        "Mid": 3,
        "Junior": 1,
        "Intern": 0,
    }

    REMOTE_KEYWORDS = {
        "Remote": 5,
        "Distributed": 5,
        "Hybrid": 3,
        "On-site": 0,
        "Office": 0,
    }

    TECH_INTEREST = {
        "Nix": 10,
        "NixOS": 10,
        "Rust": 8,
        "Go": 7,
        "Python": 5,
        "Kubernetes": 6,
    }

    def analyze_opportunity(self, result: CrawlResult) -> JobOpportunity | None:
        """
        Analyze a crawl result to see if it's a job opportunity.
        """
        # Base content analysis
        stats = self.analyze(result.url, result.content, result.headers)
        
        # Basic filter: Must have some job keywords
        content_lower = result.content.lower()
        if not any(k in content_lower for k in ["apply", "job", "career", "opening", "position"]):
            return None

        # Extract Score signals
        score = 0.0
        
        # 1. Tech Stack Match
        tech_matched = []
        for tech in stats.tech_stack:
            if tech.name in self.TECH_INTEREST:
                score += self.TECH_INTEREST[tech.name]
                tech_matched.append(tech.name)
        
        # Also check content for keywords not in TechDetector
        for tech, weight in self.TECH_INTEREST.items():
            if tech not in tech_matched and tech.lower() in content_lower:
                score += weight
                tech_matched.append(tech)

        # 2. Seniority
        detected_seniority = None
        for level, weight in self.SENIORITY_KEYWORDS.items():
            if level.lower() in content_lower:
                score += weight
                detected_seniority = level
                break # Take the highest match? No, usually highest priority first if ordered.
                
        # 3. Remote Policy
        detected_remote = None
        for policy, weight in self.REMOTE_KEYWORDS.items():
            if policy.lower() in content_lower:
                score += weight
                detected_remote = policy
                break

        # 4. Salary Extraction (Naïve regex)
        salary_range = self._extract_salary(result.content)
        if salary_range:
            score += 2 # Bonus for transparent salary

        return JobOpportunity(
            company=self._extract_company(result.url),
            url=result.url,
            title=stats.metadata.get("title"),
            seniority=detected_seniority,
            remote_policy=detected_remote,
            salary_range=salary_range,
            tech_stack=tech_matched,
            score=score,
            timestamp=result.timestamp
        )

    def _extract_salary(self, content: str) -> str | None:
        """Extract something that looks like a salary range."""
        # e.g. $100k - $150k, €50.000, 100,000 USD
        match = re.search(r'[\$€£]\s?\d{2,3}[kK]?\s?-\s?[\$€£]?\s?\d{2,3}[kK]?', content)
        return match.group(0) if match else None

    def _extract_company(self, url: str) -> str:
        """Extract company name from domain."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        parts = domain.split('.')
        if len(parts) >= 2:
            return parts[-2].title() # google.com -> Google
        return domain
