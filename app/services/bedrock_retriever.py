import boto3
import re
from strands import tool
from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

_bedrock_client = None

# Minimum relevance score — chunks below this are discarded as noise.
MIN_RELEVANCE_SCORE = 0.25

# All 50 US state abbreviations
US_STATE_ABBREVS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC"
}


def _extract_state_abbreviations(content: str) -> set[str]:
    """Extract all US state abbreviations found in the document text."""
    # Find all 2-letter uppercase words that are valid state abbreviations
    # Use word boundary to avoid matching inside longer words
    found = set()
    for match in re.finditer(r'\b([A-Z]{2})\b', content):
        abbrev = match.group(1)
        if abbrev in US_STATE_ABBREVS:
            found.add(abbrev)
    return found


# Full state name → abbreviation mapping for detecting states in user queries
_STATE_NAME_TO_ABBREV = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}


def _extract_queried_states(query: str) -> list[tuple[str, str]]:
    """Detect US state names or abbreviations in the user's query.
    
    Returns list of (state_name, state_abbreviation) tuples.
    """
    query_lower = query.lower()
    found = []
    seen_abbrevs = set()
    
    # Check full state names first (longest match first to handle "New York" before "York")
    for name, abbrev in sorted(_STATE_NAME_TO_ABBREV.items(), key=lambda x: -len(x[0])):
        if name in query_lower and abbrev not in seen_abbrevs:
            found.append((name.title(), abbrev))
            seen_abbrevs.add(abbrev)
    
    # Check for 2-letter abbreviations in the original query (case-sensitive)
    for match in re.finditer(r'\b([A-Z]{2})\b', query):
        abbrev = match.group(1)
        if abbrev in US_STATE_ABBREVS and abbrev not in seen_abbrevs:
            # Find the full name for display
            name = next((n.title() for n, a in _STATE_NAME_TO_ABBREV.items() if a == abbrev), abbrev)
            found.append((name, abbrev))
            seen_abbrevs.add(abbrev)
    
    return found


def get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client(
            'bedrock-agent-runtime',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
        )
    return _bedrock_client

def expand_query(query: str) -> str:
    search_query = query
    
    # Expand common shorthand terms to their full class code names
    shorthand_map = {
        "paper": "paperhanging",
        "hnoa": "hired and non-owned auto",
        "ebl": "employee benefits liability",
        "tria": "terrorism risk insurance",
        "bor": "broker of record",
    }
    query_lower = query.lower()
    for short, full in shorthand_map.items():
        if short in query_lower and full not in query_lower:
            search_query = f"{search_query} {full}"
            logger.info("shorthand_expanded", short=short, full=full)
    
    eligibility_keywords = ["acceptable", "eligible", "appetite", "suitability", "cover", "prohibited"]
    if any(k in query_lower for k in eligibility_keywords):
        search_query = f"{search_query} class code prohibited submit requirements eligibility"
        logger.info("query_expanded", original=query, expanded=search_query)
    return search_query

def fetch_bedrock_results(search_query: str) -> list:
    client = get_bedrock_client()
    response = client.retrieve(
        knowledgeBaseId=settings.bedrock_kb_id,
        retrievalQuery={'text': search_query},
        retrievalConfiguration={
            'vectorSearchConfiguration': {
                'numberOfResults': 10,
                'overrideSearchType': 'HYBRID'
            }
        }
    )
    return response.get('retrievalResults', [])


def _extract_chunk_metadata(content: str, metadata: dict, s3_uri: str) -> dict:
    """Extract structured metadata (url, heading, manual_type) from a retrieved chunk."""

    # ── Source URL ──
    injected_url_match = re.search(r'^SOURCE_URL:\s*(https?://\S+)', content, re.MULTILINE)
    if injected_url_match:
        url = injected_url_match.group(1).strip()
    elif 'full-page-crawl/' in s3_uri:
        filename = s3_uri.split('/')[-1].replace('.md', '.html')
        url = f"https://bindingauthority.coactionspecialty.com/manuals/{filename}"
    else:
        url = s3_uri or 'N/A'

    # ── Manual type ──
    manual_type_match = re.search(r'^MANUAL_TYPE:\s*(.+)', content, re.MULTILINE)
    manual_type = manual_type_match.group(1).strip() if manual_type_match else None

    # ── Heading (priority: CLASS_CODE > SECTION > markdown header > fallback) ──
    injected_code_match = re.search(r'^CLASS_CODE:\s*(\d+)', content, re.MULTILINE)
    section_match = re.search(r'^SECTION:\s*(.+)', content, re.MULTILINE)

    if injected_code_match:
        class_code = injected_code_match.group(1)
        heading = f"Class Code {class_code}"
        if not manual_type:
            manual_type = "General Liability"
    elif section_match:
        heading = section_match.group(1).strip().strip('_')
        if not manual_type:
            # Infer manual type from URL
            if 'property' in url.lower():
                manual_type = "Property"
            elif 'guide' in url.lower():
                manual_type = "General Liability Guide"
    else:
        header_match = re.search(r'^#+\s*(.+)', content, re.MULTILINE)
        heading = metadata.get('heading') or (header_match.group(1).strip().strip('_*') if header_match else "Manual Section")

    # Determine manual name for citation
    if manual_type:
        manual_name = f"{manual_type} Manual"
    elif 'property' in url.lower():
        manual_name = "Property Manual"
    elif 'guide' in url.lower():
        manual_name = "General Liability Guide"
    else:
        manual_name = "Binding Authority Manual"

    return {
        "url": url,
        "heading": heading,
        "manual_name": manual_name,
    }


def format_retrieved_documents(results: list, original_query: str) -> tuple[str, list[dict]]:
    """Format retrieved chunks into context for the LLM.
    
    Returns:
        tuple of (context_string, source_metadata_list)
        source_metadata_list contains dicts with keys: url, heading, manual_name
    """
    specific_codes = re.findall(r'(\d{4,})', original_query)
    
    context_parts = []
    source_metadata = []
    seen_urls = set()
    
    for res in results:
        # ── Relevance score filter ──
        score = res.get('score', 0)
        if score < MIN_RELEVANCE_SCORE:
            logger.info("chunk_filtered_low_score", score=score)
            continue

        content = res.get('content', {}).get('text', '')
        metadata = res.get('metadata', {})
        
        # ── Class code filter ──
        if specific_codes:
            found_code = any(code in content.replace(" ", "") for code in specific_codes)
            if not found_code:
                continue

        s3_uri = metadata.get('source_url') or metadata.get('sourceUrl') or ''

        # ── Extract structured metadata ──
        chunk_meta = _extract_chunk_metadata(content, metadata, s3_uri)
        
        # ── Clean content (strip metadata headers) ──
        clean_content = re.sub(r'^(SOURCE_URL|CLASS_CODE|MANUAL_TYPE|SECTION):.*\n?', '', content, flags=re.MULTILINE).strip()
        clean_content = re.sub(r'^---\s*\n', '', clean_content).strip()

        # ── Extract all US state abbreviations found in the content ──
        states_found = _extract_state_abbreviations(content)
        states_line = f"States Found in Document: {', '.join(sorted(states_found))}" if states_found else "States Found in Document: NONE"

        # ── Pre-compute state eligibility verdict if user asked about specific states ──
        queried_states = _extract_queried_states(original_query)
        eligibility_verdict = ""
        if queried_states:
            verdicts = []
            for state_name, state_abbrev in queried_states:
                if state_abbrev in states_found:
                    verdicts.append(f"  - {state_name} ({state_abbrev}): ELIGIBLE (found in document)")
                else:
                    verdicts.append(f"  - {state_name} ({state_abbrev}): NOT ELIGIBLE (not found in document)")
            eligibility_verdict = "PRE-COMPUTED STATE ELIGIBILITY (authoritative, do not override):\n" + "\n".join(verdicts)

        # ── Build context block with explicit citation info for the LLM ──
        parts_lines = [
            f"Source: {chunk_meta['url']}",
            f"Manual: {chunk_meta['manual_name']}",
            f"Heading: {chunk_meta['heading']}",
            states_line,
        ]
        if eligibility_verdict:
            parts_lines.append(eligibility_verdict)
        parts_lines.append(f"Content:\n{clean_content}")
        
        part = "\n".join(parts_lines)
        context_parts.append(part)

        # ── Track unique sources for programmatic citation ──
        if chunk_meta['url'] not in seen_urls:
            seen_urls.add(chunk_meta['url'])
            source_metadata.append(chunk_meta)
    
    if not context_parts:
        return "No relevant information found in the manuals.", []
        
    return "\n\n".join(context_parts), source_metadata


# Module-level storage for the last retrieval's source metadata.
# The agent reads this after calling search_manuals to get programmatic citations.
_last_retrieval_sources: list[dict] = []


def get_last_retrieval_sources() -> list[dict]:
    """Return source metadata from the most recent search_manuals call."""
    return list(_last_retrieval_sources)


@tool
def search_manuals(query: str) -> str:
    """Search the Coaction underwriting manuals (General Liability and Property) using the AWS Knowledge Base.

    Args:
        query: The search query to find relevant manual content.
    """
    global _last_retrieval_sources
    try:
        search_query = expand_query(query)
        results = fetch_bedrock_results(search_query)
        logger.info("retrieval_complete", result_count=len(results))
        context, sources = format_retrieved_documents(results, query)
        _last_retrieval_sources = sources
        return context
    except Exception as e:
        logger.error("bedrock_retrieval_failed", error=str(e))
        _last_retrieval_sources = []
        return f"Error searching manuals: {str(e)}"
