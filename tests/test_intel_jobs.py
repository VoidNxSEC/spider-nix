"""Tests for Job Intel module."""

import pytest
import unittest.mock
from dataclasses import dataclass
from spider_nix.intel.jobs import JobAnalyzer, JobOpportunity, CareerPageFinder
from spider_nix.crawler import CrawlResult

@dataclass
class MockSubdomain:
    subdomain: str
    alive: bool = True

class TestJobAnalyzer:
    """Test job analysis logic."""

    def test_analyze_opportunity_match(self):
        """Test detection of a good job opportunity."""
        analyzer = JobAnalyzer()
        
        content = """
        <html>
        <head><title>Senior Rust Engineer - Remote</title></head>
        <body>
            <h1>We are hiring!</h1>
            <p>We need a Senior Rust Engineer to work on NixOS systems.</p>
            <p>Requirements: Rust, Python, Kubernetes.</p>
            <p>Salary: $140k - $180k per year.</p>
            <button>Apply Now</button>
        </body>
        </html>
        """
        
        result = CrawlResult(
            url="https://careers.google.com/jobs/123",
            status_code=200,
            content=content,
            headers={}
        )
        
        opp = analyzer.analyze_opportunity(result)
        
        assert opp is not None
        assert opp.company == "Google"
        assert opp.title == "Senior Rust Engineer - Remote"
        assert opp.seniority == "Senior"
        # "Remote" in title should be caught
        assert opp.remote_policy == "Remote"
        assert opp.salary_range == "$140k - $180k"
        
        # Tech stack checks
        assert "Rust" in opp.tech_stack
        assert "NixOS" in opp.tech_stack
        assert "Kubernetes" in opp.tech_stack
        
        # Check score
        assert opp.score > 10 # Should be quite high

    def test_analyze_no_match(self):
        """Test ignoring non-job pages."""
        analyzer = JobAnalyzer()
        content = "<html><body><h1>About Us</h1><p>We make cookies.</p></body></html>"
        result = CrawlResult(url="https://example.com/about", status_code=200, content=content)
        
        opp = analyzer.analyze_opportunity(result)
        assert opp is None


class TestCareerPageFinder:
    """Test career page discovery."""

    @pytest.mark.asyncio
    async def test_find_career_pages(self):
        """Test finding pages via subdomains."""
        with unittest.mock.patch("spider_nix.intel.jobs.SubdomainEnumerator.enumerate") as mock_enum:
            # Mock subdomain results
            mock_enum.return_value = [
                MockSubdomain(subdomain="careers.example.com"),
                MockSubdomain(subdomain="jobs.example.com", alive=False)
            ]
            
            with unittest.mock.patch("spider_nix.crawler.SpiderNix.crawl") as mock_crawl:
                 finder = CareerPageFinder()
                 urls = await finder.find("example.com")
                 
                 # unique urls
                 assert len(urls) >= 2 # https/http for careers.example.com + potential paths
                 assert any("https://careers.example.com" in u for u in urls)
                 assert not any("jobs.example.com" in u for u in urls) # Not alive
