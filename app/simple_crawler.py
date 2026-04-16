"""
Simple web crawler without LlamaIndex dependency.
Returns raw HTML for cleaning and S3 upload.
"""
import asyncio
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


def _make_browser_config() -> BrowserConfig:
    return BrowserConfig(
        headless=True,
        verbose=False,
        extra_args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
    )


def _make_run_config() -> CrawlerRunConfig:
    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.48, threshold_type="fixed"),
    )
    return CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=md_generator,
        exclude_external_links=True,
        exclude_social_media_links=True,
        process_iframes=True,
        remove_overlay_elements=True,
        wait_until="networkidle",
    )


async def crawl_site_simple(
    start_url: str,
    max_depth: int | None = None,
    max_pages: int | None = None,
) -> list[dict]:
    """
    Crawl a website and return list of pages with HTML content.
    
    Returns:
        List of dicts with keys: url, title, html, depth
    """
    max_depth = max_depth or settings.max_crawl_depth
    max_pages = max_pages or settings.max_pages_per_crawl
    base_domain = urlparse(start_url).netloc

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]
    pages: list[dict] = []

    browser_cfg = _make_browser_config()
    run_cfg = _make_run_config()

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        while queue and len(visited) < max_pages:
            # Process a batch concurrently
            batch = []
            while queue and len(batch) < settings.crawl_concurrency:
                url, depth = queue.pop(0)
                if url not in visited:
                    visited.add(url)
                    batch.append((url, depth))

            if not batch:
                break

            tasks = [crawler.arun(url=url, config=run_cfg) for url, _ in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for (url, depth), result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.warning("crawl_failed", url=url, error=str(result))
                    continue

                if not result.success:
                    logger.warning("crawl_unsuccessful", url=url)
                    continue

                # Get HTML content
                html = result.html
                if not html or len(html.strip()) < 100:
                    logger.debug("skipping_thin_content", url=url)
                    continue

                # Get title
                raw_title = result.metadata.get("title") if isinstance(result.metadata, dict) else None
                title = raw_title.strip() if isinstance(raw_title, str) and raw_title.strip() else url

                pages.append({
                    "url": url,
                    "title": title,
                    "html": html,
                    "depth": depth
                })
                
                logger.info("page_crawled", url=url, depth=depth)

                # Enqueue internal links for next depth level
                if depth < max_depth and result.links:
                    internal_links = result.links.get("internal", [])
                    for link in internal_links:
                        href = link.get("href", "")
                        if href and href not in visited and urlparse(href).netloc == base_domain:
                            queue.append((href, depth + 1))

    logger.info("crawl_complete", start_url=start_url, pages=len(pages))
    return pages
