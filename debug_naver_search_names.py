import asyncio
from playwright.async_api import async_playwright

async def debug_naver_names():
    query = "이모네"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 375, "height": 812}
        )
        page = await context.new_page()
        
        url = f"https://m.map.naver.com/search2/search.naver?query={query}"
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        # Get all result items
        # Based on previous code, we look for links with /place/ or /restaurant/
        links = await page.locator('a[href*="/place/"], a[href*="/restaurant/"]').all()
        
        print(f"Found {len(links)} links.")
        
        for i, link in enumerate(links[:5]):
            print(f"\n--- Item {i+1} ---")
            # Print inner text of the link
            text = await link.inner_text()
            print(f"Link Text: {text}")
            
            # Print HTML of the link to see structure
            html = await link.evaluate("el => el.outerHTML")
            print(f"Link HTML: {html}")
            
            # Print parent HTML
            parent = link.locator("..")
            parent_html = await parent.evaluate("el => el.outerHTML")
            print(f"Parent HTML: {parent_html[:500]}...") # Truncate for readability

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_naver_names())
