from typer.testing import CliRunner
from spider_nix.cli import app
from spider_nix import __version__
from unittest.mock import patch, AsyncMock

runner = CliRunner()

def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"SpiderNix v{__version__}" in result.stdout

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Enterprise web crawler" in result.stdout

@patch('spider_nix.cli.fetch_public_proxies')
def test_proxy_fetch(mock_fetch):
    mock_fetch.return_value = ["http://1.2.3.4:8080", "http://5.6.7.8:8080"]
    
    # Run in isolation to avoid writing to actual filesystem if possible, 
    # but the command writes to proxies.txt. 
    # We can run it in a temp directory or just checks that it calls the function.
    
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["proxy-fetch"])
        assert result.exit_code == 0
        assert "Found 2 proxies" in result.stdout
        assert "Saved to: proxies.txt" in result.stdout
        
        with open("proxies.txt") as f:
            content = f.read()
            assert "http://1.2.3.4:8080" in content

