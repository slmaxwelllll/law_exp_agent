
import asyncio
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from playwright.async_api import async_playwright

class WechatSougouService():
    """通过搜狗微信搜索进行公众号数据采集"""
    def __init__(self):
        # 先不带状态，后续再考虑
        pass
    async def search_by_keyword(self,keyword : str):
        """通过搜狗微信搜索进行公众号数据采集"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto("https://weixin.sogou.com/")
            await page.fill("input[name='query']",keyword)
            # 点击搜索并等待结果页加载完成
            await page.click("input[type='submit']")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(3000)
            # 滚动到底部加载更多内容
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                pass
            await page.wait_for_timeout(1000)
            content = await page.content()
            await browser.close()
            # with open(f"search_{keyword}.html","w",encoding="utf-8") as f:
            #     f.write(content)
            return content

    async def goto_article(self, relative_web_url: list[str]) -> list[dict]:
        """通过文章相对url，跳转到文章详情页，返回 [{url, html}, ...]"""
        result = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            for url in relative_web_url:
                try:
                    await page.goto(
                        f"https://weixin.sogou.com{url}",
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                    await page.wait_for_timeout(1000)
                    result.append({"url": page.url, "html": await page.content()})
                except Exception:
                    continue
            await browser.close()
            return result
