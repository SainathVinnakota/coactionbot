import asyncio
import re
import os
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from app.logger import get_logger

logger = get_logger(__name__)

class FullPageCrawler:
    """
    Specialized crawler that preserves full pages with injected metadata.
    Designed for Amazon Bedrock Semantic Chunking.
    """

    def __init__(self, start_url: str):
        self.start_url = start_url
        self.base_domain = urlparse(start_url).netloc
        self.base_path = "/manuals/"
        self.visited = set()
        self.page_contents = {}

    def is_valid_url(self, url: str) -> bool:
        parsed = urlparse(url)
        clean = parsed._replace(fragment="").geturl()
        return (
            parsed.netloc == self.base_domain and
            parsed.path.startswith(self.base_path) and
            clean not in self.visited
        )

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        return parsed._replace(fragment="").geturl()

    def clean_text(self, text: str) -> str:
        # Remove images and noise
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text, flags=re.DOTALL)
        text = re.sub(r'AI-generated content may be incorrect\.', '', text)
        # Simplify complex links to just the text
        text = re.sub(r'\[([^\]]+)\]\(https://bindingauthority[^\)]+#[^\)]+\)', r'\1', text)
        return text.strip()

    def extract_class_code(self, url: str) -> str:
        m = re.search(r'/manuals/(\d+)\.html$', url)
        return m.group(1) if m else None

    async def _crawl_recursive(self, url: str, crawler: AsyncWebCrawler):
        norm_url = self.normalize_url(url)
        if norm_url in self.visited:
            return
        self.visited.add(norm_url)
        logger.info(f"Crawling for Ingest: {norm_url}")

        config = CrawlerRunConfig(word_count_threshold=10)
        result = await crawler.arun(url=norm_url, config=config)

        if not result.success:
            return

        cleaned = self.clean_text(result.markdown)
        
        # Inject Metadata at the top
        class_code = self.extract_class_code(norm_url)
        metadata_header = f"SOURCE_URL: {norm_url}\n"
        if class_code:
            metadata_header += f"CLASS_CODE: {class_code}\n"
        metadata_header += "--- \n\n"
        
        self.page_contents[norm_url] = metadata_header + cleaned

        # Extract links for recursion
        pattern = r'\[.*?\]\((http[s]?://[^\)]+)\)'
        links = re.findall(pattern, result.markdown)
        tasks = []
        for l in links:
            norm = self.normalize_url(l)
            if self.is_valid_url(norm):
                tasks.append(self._crawl_recursive(norm, crawler))
        
        if tasks:
            await asyncio.gather(*tasks)

    async def run(self) -> dict:
        """Runs the crawler and returns a map of {url: full_content}."""
        async with AsyncWebCrawler() as crawler:
            await self._crawl_recursive(self.start_url, crawler)
        return self.page_contents

if __name__ == "__main__":
    async def fast_run():
        start_url = "https://bindingauthority.coactionspecialty.com/manuals/guide.html"
        output_dir = "data/bedrock_ingest/full_manuals"
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            
        print(f"--- Starting recovery crawl from {start_url} ---")
        crawler = FullPageCrawler(start_url)
        pages = await crawler.run()
        
        print(f"Crawled {len(pages)} pages. Saving to {output_dir}...")
        for url, content in pages.items():
            # Get the page name (e.g., 44280.html -> 44280.md)
            name = url.split('/')[-1].replace('.html', '.md')
            if not name: name = "index.md"
            
            with open(os.path.join(output_dir, name), 'w', encoding='utf-8') as f:
                f.write(content)
        
        print(f"SUCCESS: {len(pages)} class code files recovered!")

    asyncio.run(fast_run())
