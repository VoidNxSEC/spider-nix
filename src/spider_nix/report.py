"""HTML report generation with visualizations for crawl results."""

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .monitor import CrawlStatistics
from .storage import CrawlResult


class HTMLReportGenerator:
    """Generate beautiful HTML reports with charts and statistics."""

    def __init__(self):
        self.template = self._get_template()

    def generate(
        self,
        results: list[CrawlResult],
        stats: CrawlStatistics | None = None,
        output_path: str = "report.html",
        title: str = "SpiderNix Crawl Report",
    ):
        """
        Generate HTML report from crawl results.

        Args:
            results: List of crawl results
            stats: Optional crawl statistics
            output_path: Path to save HTML report
            title: Report title
        """
        # Analyze results
        analysis = self._analyze_results(results, stats)

        # Prepare chart data
        charts_data = self._prepare_charts(analysis)

        # Render HTML
        html = self.template.format(
            title=title,
            generated_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            summary_html=self._render_summary(analysis),
            status_codes_chart=charts_data["status_codes"],
            response_time_chart=charts_data["response_times"],
            timeline_chart=charts_data["timeline"],
            results_table=self._render_results_table(results[:100]),
        )

        # Write to file
        output_file = Path(output_path)
        output_file.write_text(html, encoding="utf-8")

        return output_file

    def _analyze_results(
        self,
        results: list[CrawlResult],
        stats: CrawlStatistics | None,
    ) -> dict[str, Any]:
        """Analyze crawl results for reporting."""
        if not results:
            return {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "status_codes": {},
                "response_times": [],
                "domains": {},
            }

        status_codes = Counter(r.status_code for r in results)
        successful = sum(1 for r in results if 200 <= r.status_code < 300)
        failed = len(results) - successful

        # Extract response times
        response_times = []
        for r in results:
            if "elapsed_ms" in r.metadata:
                response_times.append(r.metadata["elapsed_ms"])

        # Domain distribution
        from urllib.parse import urlparse

        domains = Counter(urlparse(r.url).netloc for r in results)

        # Timeline data (group by minute)
        timeline = defaultdict(int)
        for r in results:
            if r.timestamp:
                minute = r.timestamp[:16]  # YYYY-MM-DD HH:MM
                timeline[minute] += 1

        return {
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / len(results) * 100) if results else 0,
            "status_codes": dict(status_codes),
            "response_times": response_times,
            "avg_response_time": sum(response_times) / len(response_times)
            if response_times
            else 0,
            "domains": dict(domains.most_common(10)),
            "timeline": dict(sorted(timeline.items())),
            "stats": stats,
        }

    def _prepare_charts(self, analysis: dict[str, Any]) -> dict[str, str]:
        """Prepare Chart.js data."""
        # Status codes chart
        status_codes = analysis["status_codes"]
        status_codes_data = {
            "labels": [str(code) for code in sorted(status_codes.keys())],
            "data": [status_codes[code] for code in sorted(status_codes.keys())],
        }

        # Response times histogram
        response_times = analysis["response_times"]
        if response_times:
            # Create buckets
            buckets = [0, 500, 1000, 2000, 5000, 10000, float("inf")]
            bucket_labels = ["0-500ms", "500-1000ms", "1-2s", "2-5s", "5-10s", ">10s"]
            bucket_counts = [0] * (len(buckets) - 1)

            for rt in response_times:
                for i in range(len(buckets) - 1):
                    if buckets[i] <= rt < buckets[i + 1]:
                        bucket_counts[i] += 1
                        break

            response_time_data = {
                "labels": bucket_labels,
                "data": bucket_counts,
            }
        else:
            response_time_data = {"labels": [], "data": []}

        # Timeline chart
        timeline = analysis["timeline"]
        timeline_data = {
            "labels": list(timeline.keys()),
            "data": list(timeline.values()),
        }

        return {
            "status_codes": json.dumps(status_codes_data),
            "response_times": json.dumps(response_time_data),
            "timeline": json.dumps(timeline_data),
        }

    def _render_summary(self, analysis: dict[str, Any]) -> str:
        """Render summary section."""
        success_rate = analysis["success_rate"]
        success_class = "success" if success_rate >= 80 else "warning" if success_rate >= 60 else "danger"

        html = f"""
        <div class="stat-card">
            <h3>Total Requests</h3>
            <div class="stat-value">{analysis['total']}</div>
        </div>
        <div class="stat-card">
            <h3>Successful</h3>
            <div class="stat-value success">{analysis['successful']}</div>
        </div>
        <div class="stat-card">
            <h3>Failed</h3>
            <div class="stat-value danger">{analysis['failed']}</div>
        </div>
        <div class="stat-card">
            <h3>Success Rate</h3>
            <div class="stat-value {success_class}">{success_rate:.1f}%</div>
        </div>
        <div class="stat-card">
            <h3>Avg Response Time</h3>
            <div class="stat-value">{analysis['avg_response_time']:.0f}ms</div>
        </div>
        """

        # Add stats if available
        if analysis["stats"]:
            stats = analysis["stats"]
            html += f"""
            <div class="stat-card">
                <h3>Requests/sec</h3>
                <div class="stat-value">{stats.requests_per_second():.2f}</div>
            </div>
            <div class="stat-card">
                <h3>Duplicates Skipped</h3>
                <div class="stat-value">{stats.duplicate_urls + stats.duplicate_content}</div>
            </div>
            """

        return html

    def _render_results_table(self, results: list[CrawlResult]) -> str:
        """Render results table (limited to first 100)."""
        if not results:
            return "<p>No results to display.</p>"

        html = """
        <table>
            <thead>
                <tr>
                    <th>URL</th>
                    <th>Status</th>
                    <th>Response Time</th>
                    <th>Size</th>
                    <th>Timestamp</th>
                </tr>
            </thead>
            <tbody>
        """

        for r in results:
            status_class = "success" if 200 <= r.status_code < 300 else "warning" if 300 <= r.status_code < 400 else "danger"
            elapsed = r.metadata.get("elapsed_ms", 0)
            size = len(r.content) if r.content else 0
            size_kb = size / 1024

            html += f"""
                <tr>
                    <td class="url-cell" title="{r.url}">{r.url[:80]}...</td>
                    <td class="{status_class}">{r.status_code}</td>
                    <td>{elapsed:.0f}ms</td>
                    <td>{size_kb:.1f} KB</td>
                    <td>{r.timestamp[:19] if r.timestamp else 'N/A'}</td>
                </tr>
            """

        html += """
            </tbody>
        </table>
        """

        if len(results) > 100:
            html += f"<p class='note'>Showing first 100 of {len(results)} results.</p>"

        return html

    def _get_template(self) -> str:
        """Get HTML template."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            padding: 2rem;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }}
        header h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }}
        header .subtitle {{
            opacity: 0.9;
            font-size: 1rem;
        }}
        .content {{
            padding: 2rem;
        }}
        h2 {{
            color: #667eea;
            margin: 2rem 0 1rem;
            font-size: 1.8rem;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: #f8f9fa;
            padding: 1.5rem;
            border-radius: 12px;
            text-align: center;
            border-left: 4px solid #667eea;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .stat-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }}
        .stat-card h3 {{
            font-size: 0.9rem;
            text-transform: uppercase;
            color: #666;
            margin-bottom: 0.5rem;
            letter-spacing: 0.5px;
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #333;
        }}
        .stat-value.success {{
            color: #28a745;
        }}
        .stat-value.warning {{
            color: #ffc107;
        }}
        .stat-value.danger {{
            color: #dc3545;
        }}
        .chart-container {{
            background: #f8f9fa;
            padding: 2rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            height: 400px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
            background: white;
        }}
        table thead {{
            background: #667eea;
            color: white;
        }}
        table th {{
            padding: 1rem;
            text-align: left;
            font-weight: 600;
        }}
        table td {{
            padding: 0.75rem 1rem;
            border-bottom: 1px solid #e9ecef;
        }}
        table tbody tr:hover {{
            background: #f8f9fa;
        }}
        .url-cell {{
            max-width: 400px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .success {{
            color: #28a745;
            font-weight: bold;
        }}
        .warning {{
            color: #ffc107;
            font-weight: bold;
        }}
        .danger {{
            color: #dc3545;
            font-weight: bold;
        }}
        .note {{
            text-align: center;
            color: #666;
            font-style: italic;
            margin-top: 1rem;
        }}
        footer {{
            text-align: center;
            padding: 2rem;
            color: #666;
            border-top: 1px solid #e9ecef;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🕷️ {title}</h1>
            <div class="subtitle">Generated: {generated_time}</div>
        </header>

        <div class="content">
            <h2>📊 Summary</h2>
            <div class="stats-grid">
                {summary_html}
            </div>

            <h2>📈 Status Code Distribution</h2>
            <div class="chart-container">
                <canvas id="statusCodesChart"></canvas>
            </div>

            <h2>⏱️ Response Time Distribution</h2>
            <div class="chart-container">
                <canvas id="responseTimeChart"></canvas>
            </div>

            <h2>📅 Requests Timeline</h2>
            <div class="chart-container">
                <canvas id="timelineChart"></canvas>
            </div>

            <h2>🔍 Crawl Results</h2>
            {results_table}
        </div>

        <footer>
            <p>Generated by <strong>SpiderNix</strong> - Enterprise OSINT Crawler</p>
        </footer>
    </div>

    <script>
        // Status Codes Chart
        const statusCodesData = {status_codes_chart};
        new Chart(document.getElementById('statusCodesChart'), {{
            type: 'bar',
            data: {{
                labels: statusCodesData.labels,
                datasets: [{{
                    label: 'Request Count',
                    data: statusCodesData.data,
                    backgroundColor: 'rgba(102, 126, 234, 0.7)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{ beginAtZero: true }}
                }}
            }}
        }});

        // Response Time Chart
        const responseTimeData = {response_time_chart};
        new Chart(document.getElementById('responseTimeChart'), {{
            type: 'bar',
            data: {{
                labels: responseTimeData.labels,
                datasets: [{{
                    label: 'Request Count',
                    data: responseTimeData.data,
                    backgroundColor: 'rgba(40, 167, 69, 0.7)',
                    borderColor: 'rgba(40, 167, 69, 1)',
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{ beginAtZero: true }}
                }}
            }}
        }});

        // Timeline Chart
        const timelineData = {timeline_chart};
        new Chart(document.getElementById('timelineChart'), {{
            type: 'line',
            data: {{
                labels: timelineData.labels,
                datasets: [{{
                    label: 'Requests per Minute',
                    data: timelineData.data,
                    backgroundColor: 'rgba(255, 193, 7, 0.2)',
                    borderColor: 'rgba(255, 193, 7, 1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{ beginAtZero: true }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""


def generate_report(
    results: list[CrawlResult],
    output_path: str = "report.html",
    title: str = "SpiderNix Crawl Report",
    stats: CrawlStatistics | None = None,
) -> Path:
    """
    Generate HTML report from crawl results.

    Args:
        results: List of crawl results
        output_path: Path to save HTML report
        title: Report title
        stats: Optional crawl statistics

    Returns:
        Path to generated report
    """
    generator = HTMLReportGenerator()
    return generator.generate(results, stats, output_path, title)
