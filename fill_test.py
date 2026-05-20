"""Auto-generated Playwright script for form filling."""
import asyncio
from playwright.async_api import async_playwright


async def fill_forms():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto('https://httpbin.org/forms/post')
        await page.wait_for_load_state('networkidle')

        # Form 1: login
        # Action: /post
        await page.fill('[name="custtel"]', '+5511999999999')
        await page.fill('[name="custemail"]', 'joao@example.com')
        # Uncomment to submit:
        # await page.click('[type="submit"]')

        # Keep browser open for review
        await asyncio.sleep(30)
        await browser.close()


asyncio.run(fill_forms())