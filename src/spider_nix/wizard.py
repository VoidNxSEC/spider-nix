"""Interactive configuration wizard for spider-nix."""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from .config import (
    PRESETS,
    CrawlerConfig,
    ProxyConfig,
    StealthConfig,
    get_preset,
    list_presets,
)


class ConfigurationWizard:
    """Interactive wizard for creating crawler configurations."""

    def __init__(self):
        self.console = Console()

    def run(self) -> CrawlerConfig:
        """Run the configuration wizard and return a CrawlerConfig."""
        self._print_welcome()

        # Step 1: Choose preset or custom
        use_preset = Confirm.ask(
            "\n[cyan]Would you like to start from a preset configuration?[/]",
            default=True,
        )

        if use_preset:
            config = self._choose_preset()
            customize = Confirm.ask(
                "\n[cyan]Would you like to customize this preset?[/]",
                default=False,
            )
            if not customize:
                return config
        else:
            config = CrawlerConfig()

        # Step 2: Customize configuration
        self._customize_basic_settings(config)
        self._customize_stealth_settings(config)
        self._customize_proxy_settings(config)
        self._customize_browser_settings(config)
        self._customize_output_settings(config)

        # Step 3: Review and confirm
        self._print_summary(config)

        confirm = Confirm.ask(
            "\n[cyan]Save this configuration?[/]",
            default=True,
        )

        if not confirm:
            self.console.print("[yellow]Configuration cancelled.[/]")
            return CrawlerConfig()

        return config

    def _print_welcome(self):
        """Print welcome message."""
        welcome_text = Text()
        welcome_text.append("SpiderNix Configuration Wizard\n", style="bold cyan")
        welcome_text.append("\n")
        welcome_text.append(
            "This wizard will help you create a custom crawler configuration.\n",
            style="white",
        )
        welcome_text.append(
            "You can start from a preset or build from scratch.\n",
            style="white",
        )

        self.console.print(
            Panel(
                welcome_text,
                title="[bold]Welcome[/]",
                border_style="cyan",
            )
        )

    def _choose_preset(self) -> CrawlerConfig:
        """Let user choose a preset configuration."""
        presets_info = list_presets()

        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Preset", style="cyan", width=15)
        table.add_column("Description", style="white")

        for preset_name, description in presets_info.items():
            table.add_row(preset_name, description)

        self.console.print("\n")
        self.console.print(table)
        self.console.print("\n")

        preset_name = Prompt.ask(
            "[cyan]Choose a preset[/]",
            choices=list(PRESETS.keys()),
            default="balanced",
        )

        config = get_preset(preset_name)
        self.console.print(
            f"\n[green]✓[/] Loaded preset: [bold]{preset_name}[/]"
        )

        return config

    def _customize_basic_settings(self, config: CrawlerConfig):
        """Customize basic crawler settings."""
        self.console.print("\n")
        self.console.rule("[bold cyan]Basic Settings[/]", style="cyan")

        customize = Confirm.ask(
            "\n[cyan]Customize basic settings (pages, concurrency, timeouts)?[/]",
            default=False,
        )

        if not customize:
            return

        config.max_requests_per_crawl = IntPrompt.ask(
            "[cyan]Max pages to crawl[/]",
            default=config.max_requests_per_crawl,
        )

        config.max_concurrent_requests = IntPrompt.ask(
            "[cyan]Max concurrent requests[/]",
            default=config.max_concurrent_requests,
        )

        config.request_timeout_ms = IntPrompt.ask(
            "[cyan]Request timeout (milliseconds)[/]",
            default=config.request_timeout_ms,
        )

        config.max_retries = IntPrompt.ask(
            "[cyan]Max retries per request[/]",
            default=config.max_retries,
        )

    def _customize_stealth_settings(self, config: CrawlerConfig):
        """Customize stealth/anti-detection settings."""
        self.console.print("\n")
        self.console.rule("[bold cyan]Stealth Settings[/]", style="cyan")

        customize = Confirm.ask(
            "\n[cyan]Customize stealth/anti-detection settings?[/]",
            default=False,
        )

        if not customize:
            return

        config.stealth.randomize_user_agent = Confirm.ask(
            "[cyan]Randomize user agent?[/]",
            default=config.stealth.randomize_user_agent,
        )

        config.stealth.randomize_fingerprint = Confirm.ask(
            "[cyan]Randomize browser fingerprint?[/]",
            default=config.stealth.randomize_fingerprint,
        )

        config.stealth.human_like_delays = Confirm.ask(
            "[cyan]Enable human-like delays between requests?[/]",
            default=config.stealth.human_like_delays,
        )

        if config.stealth.human_like_delays:
            config.stealth.min_delay_ms = IntPrompt.ask(
                "[cyan]Minimum delay (milliseconds)[/]",
                default=config.stealth.min_delay_ms,
            )

            config.stealth.max_delay_ms = IntPrompt.ask(
                "[cyan]Maximum delay (milliseconds)[/]",
                default=config.stealth.max_delay_ms,
            )

    def _customize_proxy_settings(self, config: CrawlerConfig):
        """Customize proxy settings."""
        self.console.print("\n")
        self.console.rule("[bold cyan]Proxy Settings[/]", style="cyan")

        use_proxies = Confirm.ask(
            "\n[cyan]Do you want to use proxy rotation?[/]",
            default=bool(config.proxy.urls),
        )

        if not use_proxies:
            config.proxy.urls = []
            return

        self.console.print(
            "\n[dim]Enter proxy URLs one by one. Press Enter with empty input to finish.[/]"
        )

        proxies = []
        while True:
            proxy = Prompt.ask(
                f"[cyan]Proxy URL {len(proxies) + 1}[/]",
                default="",
            )

            if not proxy:
                break

            proxies.append(proxy)

        config.proxy.urls = proxies

        if proxies:
            config.proxy.rotation_strategy = Prompt.ask(
                "[cyan]Proxy rotation strategy[/]",
                choices=["round_robin", "random", "least_used"],
                default=config.proxy.rotation_strategy,
            )

            config.proxy.rotate_on_block = Confirm.ask(
                "[cyan]Rotate proxy on block (429, 503)?[/]",
                default=config.proxy.rotate_on_block,
            )

    def _customize_browser_settings(self, config: CrawlerConfig):
        """Customize browser settings."""
        self.console.print("\n")
        self.console.rule("[bold cyan]Browser Settings[/]", style="cyan")

        config.use_browser = Confirm.ask(
            "\n[cyan]Use browser (Playwright) for JavaScript rendering?[/]",
            default=config.use_browser,
        )

        if config.use_browser:
            config.headless = Confirm.ask(
                "[cyan]Run browser in headless mode?[/]",
                default=config.headless,
            )

            config.browser_type = Prompt.ask(
                "[cyan]Browser type[/]",
                choices=["chromium", "firefox", "webkit"],
                default=config.browser_type,
            )

    def _customize_output_settings(self, config: CrawlerConfig):
        """Customize output settings."""
        self.console.print("\n")
        self.console.rule("[bold cyan]Output Settings[/]", style="cyan")

        config.output_format = Prompt.ask(
            "\n[cyan]Output format[/]",
            choices=["json", "csv", "sqlite"],
            default=config.output_format,
        )

        config.output_path = Prompt.ask(
            "[cyan]Output directory path[/]",
            default=config.output_path,
        )

    def _print_summary(self, config: CrawlerConfig):
        """Print configuration summary."""
        self.console.print("\n")
        self.console.rule("[bold cyan]Configuration Summary[/]", style="cyan")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Setting", style="cyan", width=30)
        table.add_column("Value", style="white")

        # Basic settings
        table.add_row("[bold]BASIC SETTINGS[/]", "")
        table.add_row("Max Pages", str(config.max_requests_per_crawl))
        table.add_row("Concurrent Requests", str(config.max_concurrent_requests))
        table.add_row("Request Timeout", f"{config.request_timeout_ms}ms")
        table.add_row("Max Retries", str(config.max_retries))

        table.add_row("", "")
        table.add_row("[bold]STEALTH SETTINGS[/]", "")
        table.add_row(
            "Randomize User Agent",
            "✓ Yes" if config.stealth.randomize_user_agent else "✗ No",
        )
        table.add_row(
            "Randomize Fingerprint",
            "✓ Yes" if config.stealth.randomize_fingerprint else "✗ No",
        )
        table.add_row(
            "Human-like Delays",
            "✓ Yes" if config.stealth.human_like_delays else "✗ No",
        )
        if config.stealth.human_like_delays:
            table.add_row(
                "Delay Range",
                f"{config.stealth.min_delay_ms}ms - {config.stealth.max_delay_ms}ms",
            )

        table.add_row("", "")
        table.add_row("[bold]PROXY SETTINGS[/]", "")
        table.add_row("Proxies", str(len(config.proxy.urls)))
        if config.proxy.urls:
            table.add_row("Rotation Strategy", config.proxy.rotation_strategy)
            table.add_row(
                "Rotate on Block",
                "✓ Yes" if config.proxy.rotate_on_block else "✗ No",
            )

        table.add_row("", "")
        table.add_row("[bold]BROWSER SETTINGS[/]", "")
        table.add_row("Use Browser", "✓ Yes" if config.use_browser else "✗ No")
        if config.use_browser:
            table.add_row("Headless", "✓ Yes" if config.headless else "✗ No")
            table.add_row("Browser Type", config.browser_type)

        table.add_row("", "")
        table.add_row("[bold]OUTPUT SETTINGS[/]", "")
        table.add_row("Format", config.output_format)
        table.add_row("Path", config.output_path)

        self.console.print("\n")
        self.console.print(
            Panel(
                table,
                title="[bold]Your Configuration[/]",
                border_style="green",
            )
        )


def run_wizard() -> CrawlerConfig:
    """
    Run the interactive configuration wizard.

    Returns:
        CrawlerConfig instance based on user choices
    """
    wizard = ConfigurationWizard()
    return wizard.run()


if __name__ == "__main__":
    config = run_wizard()
    print("\nFinal configuration:")
    print(config.model_dump_json(indent=2))
