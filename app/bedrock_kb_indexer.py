"""
Bedrock Knowledge Base indexer.
Crawls websites, cleans HTML, and uploads to S3.
"""
import asyncio
from app.simple_crawler import crawl_site_simple
from app.html_cleaner import clean_html, get_s3_key
from app.s3_uploader import S3Uploader
from app.logger import get_logger

logger = get_logger(__name__)


async def index_url_to_bedrock_kb(
    url: str,
    max_depth: int | None = None,
    max_pages: int | None = None
) -> dict:
    """
    Crawl a URL and upload cleaned content to S3 for Bedrock KB ingestion.
    
    Args:
        url: Starting URL to crawl
        max_depth: Maximum crawl depth
        max_pages: Maximum pages to crawl
        
    Returns:
        Summary dict with pages_crawled and documents_uploaded
    """
    logger.info("bedrock_kb_indexing_started", url=url)
    
    # Crawl the site
    pages = await crawl_site_simple(url, max_depth=max_depth, max_pages=max_pages)
    if not pages:
        logger.warning("no_pages_crawled", url=url)
        return {"pages_crawled": 0, "documents_uploaded": 0}
    
    logger.info("crawl_done", pages=len(pages))
    
    # Prepare documents for S3 upload
    uploader = S3Uploader()
    upload_batch = []
    
    for page in pages:
        # Clean HTML and prepare for upload
        cleaned_content = clean_html(page["html"], page["url"], page["title"])
        if cleaned_content:
            s3_key = get_s3_key(page["url"])
            upload_batch.append((cleaned_content, s3_key))
    
    # Upload to S3
    result = uploader.batch_upload(upload_batch)
    logger.info("bedrock_kb_indexing_done", result=result)
    
    return {
        "pages_crawled": len(pages),
        "documents_uploaded": result["uploaded"],
        "upload_failures": result["failed"]
    }
