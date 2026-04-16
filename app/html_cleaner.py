"""
HTML cleaning utilities for web content.
Strips boilerplate and formats content for Bedrock Knowledge Base.
"""
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from slugify import slugify
from urllib.parse import urlparse
import re

# HTML tags that contain boilerplate — always strip these
BOILERPLATE_TAGS = [
    'nav', 'footer', 'header', 'aside', 'form',
    'script', 'style', 'noscript', 'iframe',
    'cookie-banner', 'advertisement'
]

# CSS classes/IDs that indicate nav/footer noise
BOILERPLATE_PATTERNS = [
    'nav', 'footer', 'header', 'sidebar', 'cookie',
    'banner', 'advertisement', 'popup', 'modal',
    'breadcrumb', 'pagination', 'social-share'
]


def clean_html(raw_html: str, source_url: str, page_title: str = '') -> str:
    """
    Takes raw HTML from crawl4ai, strips boilerplate, returns clean text
    with metadata frontmatter ready for S3 upload.
    
    Args:
        raw_html: Raw HTML content
        source_url: Original URL of the page
        page_title: Page title (optional)
        
    Returns:
        Cleaned text with metadata frontmatter
    """
    soup = BeautifulSoup(raw_html, 'html.parser')
    
    # Remove boilerplate tags entirely
    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    
    # Remove elements whose class or id suggests boilerplate
    for pattern in BOILERPLATE_PATTERNS:
        for el in soup.find_all(class_=re.compile(pattern, re.I)):
            el.decompose()
        for el in soup.find_all(id=re.compile(pattern, re.I)):
            el.decompose()
    
    # Extract main content — prefer semantic tags, fallback to body
    main_content = (
        soup.find('main') or
        soup.find('article') or
        soup.find(id=re.compile(r'content|main', re.I)) or
        soup.find(class_=re.compile(r'content|main', re.I)) or
        soup.body
    )
    
    if not main_content:
        return ''
    
    # Get clean text
    text = main_content.get_text(separator='\n', strip=True)
    
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove lines that are purely noise (single chars, just numbers, etc.)
    lines = [l for l in text.split('\n') if len(l.strip()) > 3]
    text = '\n'.join(lines)
    
    # Build metadata frontmatter — Bedrock KB preserves this for citations
    frontmatter = f"""source_url: {source_url}
title: {page_title or 'Untitled'}
last_crawled: {datetime.now(timezone.utc).isoformat()}
slug: {slugify(source_url)}

"""
    
    return frontmatter + text


def get_s3_key(url: str) -> str:
    """
    Returns S3 key in format: web/{domain}/{slug}.txt
    
    Args:
        url: Source URL
        
    Returns:
        S3 object key
    """
    parsed = urlparse(url)
    domain = parsed.netloc.replace('www.', '')
    slug = slugify(parsed.path) or 'index'
    return f"web/{domain}/{slug}.txt"
