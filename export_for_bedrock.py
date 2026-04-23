import asyncio
import os
import sys
from urllib.parse import urlparse
from app.crawlers.full_page_crawler import FullPageCrawler

async def main():
    start_url = "https://bindingauthority.coactionspecialty.com/manuals/property.html"
    if len(sys.argv) > 1:
        start_url = sys.argv[1]

    # Create a domain-specific sub-folder to avoid overwriting files
    domain = urlparse(start_url).netloc.replace('.', '_')
    output_dir = os.path.join("data/bedrock_ingest", domain)
    os.makedirs(output_dir, exist_ok=True)

    print(f"🚀 Starting Full-Page Crawl: {start_url}")
    crawler = FullPageCrawler(start_url)
    pages = await crawler.run()

    print(f"\n📂 Saving {len(pages)} pages to {output_dir}...")
    
    for url, content in pages.items():
        # Create a safe filename from the URL path
        parsed_url = urlparse(url)
        path_parts = [p for p in parsed_url.path.split('/') if p]
        
        if not path_parts:
            filename = "index.md"
        else:
            filename = path_parts[-1]
            if filename == "manuals":
                filename = "index.md"
        
        if not filename.endswith(".md") and not filename.endswith(".html"):
            filename += ".md"
        filename = filename.replace(".html", ".md")
        
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
    print(f"Export Complete! Files ready for S3 upload in {output_dir}")

if __name__ == "__main__":
    asyncio.run(main())
