import json
import threading
import redis
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

_lock = threading.Lock()


class JobCache:
    _client: redis.Redis | None = None
    _DEFAULT_TTL_DAYS = 180

    @classmethod
    def connect(cls, host: str, port: int, password: str | None = None) -> None:
        """Call once at app startup to initialize the shared Redis client."""
        with _lock:
            if cls._client is None:
                cls._client = redis.Redis(
                    host=host,
                    port=port,
                    password=password or None,
                    decode_responses=True,
                )

    @classmethod
    def _client_or_raise(cls) -> redis.Redis:
        if cls._client is None:
            raise RuntimeError("JobCache not initialized. Call JobCache.connect() first.")
        return cls._client

    @classmethod
    def get_job(cls, job_id: str) -> dict | None:
        """Fetch a cached job result. Returns None if not found or expired."""
        data = cls._client_or_raise().get(f"job:{job_id}")
        return json.loads(data) if data else None

    @classmethod
    def set_job(cls, job_id: str, result: dict, ttl_days: int = _DEFAULT_TTL_DAYS) -> None:
        """Cache a job result with a TTL. Defaults to 180 days (6 months)."""
        cls._client_or_raise().setex(
            name=f"job:{job_id}",
            time=timedelta(days=ttl_days),
            value=json.dumps(result),
        )


def main():
    try:
        logger.info("Starting Job Cache")
        JobCache.connect(host="localhost", port=6379)
        JobCache.set_job("123", {"job_id": "123", "job_title": "Test Job"})
        result = JobCache.get_job("123")
        logger.info(f"Fetched job: {result}")
    except Exception as e:
        logger.error(f"Error: {e}")
        import sys
        sys.exit(1)


if __name__ == "__main__":
    from logger import setup_logging
    setup_logging()
    main()
