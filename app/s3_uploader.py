"""
S3 uploader for cleaned web content.
Stores documents in S3 for Bedrock Knowledge Base ingestion.
"""
import boto3
from botocore.exceptions import ClientError
from app.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)


class S3Uploader:
    """Uploads cleaned web content to S3 for Bedrock KB ingestion."""

    def __init__(self, bucket_name: str | None = None):
        """
        Initialize S3 uploader.
        
        Args:
            bucket_name: S3 bucket name (defaults to settings.s3_bucket_name)
        """
        settings = get_settings()
        self.bucket_name = bucket_name or settings.s3_bucket_name
        
        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        
        logger.info("s3_uploader_initialized", bucket=self.bucket_name)

    def upload_document(self, content: str, s3_key: str) -> bool:
        """
        Upload document content to S3.
        
        Args:
            content: Document text with metadata frontmatter
            s3_key: S3 object key (e.g., "web/example.com/page.txt")
            
        Returns:
            True if upload successful, False otherwise
        """
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content.encode('utf-8'),
                ContentType='text/plain',
                Metadata={
                    'source': 'web-crawler',
                    'content-type': 'cleaned-html'
                }
            )
            logger.info("document_uploaded", s3_key=s3_key)
            return True
        except ClientError as e:
            logger.error("upload_failed", s3_key=s3_key, error=str(e))
            return False

    def batch_upload(self, documents: list[tuple[str, str]]) -> dict:
        """
        Upload multiple documents to S3.
        
        Args:
            documents: List of (content, s3_key) tuples
            
        Returns:
            Summary dict with uploaded and failed counts
        """
        uploaded = 0
        failed = 0
        
        for content, s3_key in documents:
            if self.upload_document(content, s3_key):
                uploaded += 1
            else:
                failed += 1
        
        logger.info("batch_upload_complete", uploaded=uploaded, failed=failed)
        return {"uploaded": uploaded, "failed": failed}
