import uuid
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.models import CrawlRequest, CrawlResponse, CrawlStatus, QueryRequest, QueryResponse
from app.logger import get_logger
from app.bedrock_kb_indexer import index_url_to_bedrock_kb

logger = get_logger(__name__)
router = APIRouter()

_jobs: dict[str, CrawlResponse] = {}
_session_manager = None
_conversational_agent = None


def set_dependencies(session_manager, conversational_agent):
    global _session_manager, _conversational_agent
    _session_manager = session_manager
    _conversational_agent = conversational_agent


async def _run_indexing_job(job_id: str, url: str, max_depth: int | None, max_pages: int | None):
    job = _jobs[job_id]
    job.status = CrawlStatus.CRAWLING
    try:
        # Crawl, clean, and upload to S3
        result = await index_url_to_bedrock_kb(url, max_depth=max_depth, max_pages=max_pages)
        job.status = CrawlStatus.DONE
        job.pages_crawled = result["pages_crawled"]
        job.chunks_indexed = result["documents_uploaded"]
        job.message = (
            f"Uploaded {result['documents_uploaded']} documents from {result['pages_crawled']} pages to S3. "
            f"Run ingestion job to sync with Bedrock KB."
        )
        logger.info("indexing_job_completed", job_id=job_id, **result)
    except Exception as e:
        job.status = CrawlStatus.FAILED
        job.message = str(e)
        logger.error("job_failed", job_id=job_id, error=str(e))


@router.post("/crawl", response_model=CrawlResponse, status_code=202)
async def crawl_and_index(request: CrawlRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    url = str(request.url)
    job = CrawlResponse(job_id=job_id, status=CrawlStatus.PENDING, url=url, message="Job queued.")
    _jobs[job_id] = job
    background_tasks.add_task(_run_indexing_job, job_id=job_id, url=url,
                               max_depth=request.max_depth, max_pages=request.max_pages)
    logger.info("job_queued", job_id=job_id, url=url)
    return job


@router.get("/crawl/{job_id}", response_model=CrawlResponse)
async def get_job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_base(request: QueryRequest):
    try:
        session_id = request.session_id
        if not session_id:
            if _session_manager is None:
                raise HTTPException(status_code=500, detail="Session manager not initialized")
            session_id = _session_manager.create_session()
            logger.info("auto_created_session", session_id=session_id)

        answer, sources, follow_up_questions = await _conversational_agent.query(
            session_id=session_id,
            query=request.query,
            top_k=request.top_k,
        )

        return QueryResponse(
            query=request.query,
            answer=answer,
            sources=sources,
            session_id=session_id,
            follow_up_questions=follow_up_questions,
        )
    except Exception as e:
        logger.error("query_failed", query=request.query, error=str(e))
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


