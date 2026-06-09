
import asyncio
import random
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from playwright.async_api import async_playwright


class WechatSougouService():
    """通过搜狗微信搜索进行公众号数据采集（单浏览器会话，防风控）"""

    async def search_and_fetch_articles(self, keyword: str) -> tuple[str, list[dict]]:
        """
        一次浏览器会话完成：搜索 + 逐篇跳转抓正文。
        返回 (搜索结果页HTML, [{url, html}, ...])
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            # 1. 搜索
            await page.goto("https://weixin.sogou.com/")
            await page.fill("input[name='query']", keyword)
            await page.click("input[type='submit']")
            await page.wait_for_load_state("networkidle")           
            await page.wait_for_timeout(3000)
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                pass
            # 尝试翻到第二页（如果存在）
            try:
                await page.click("#sogou_next")
                await page.wait_for_load_state("networkidle")
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                except Exception:
                    pass
                await page.wait_for_timeout(1000)
                second_page_html = await page.content()
                search_html = second_page_html
            except Exception:
                # 无第二页，只用第一页
                print("无第二页")
                await page.close()

            # 2. 从搜索页提取文章相对 URL
            from wechat_service.data_parse import HtmlParseStrategy
            url_list = HtmlParseStrategy().parse(search_html)

            # 3. 同一浏览器内逐篇跳转文章详情页（带随机延迟防风控）
            articles = []
            for url in url_list[:10]:
                try:
                    await page.goto(
                        f"https://weixin.sogou.com{url}",
                        wait_until="domcontentloaded",
                        timeout=20000,
                    )
                    await page.wait_for_timeout(random.randint(2000, 4000))
                    articles.append({"url": page.url, "html": await page.content()})
                except Exception:
                    continue

            await browser.close()
            return search_html, articles
