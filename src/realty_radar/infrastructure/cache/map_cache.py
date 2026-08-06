"""Redis 인메모리 캐시를 이용한 지도 뷰포트 및 마커 캐싱 서비스."""
from __future__ import annotations

import json
import logging
from typing import Any

from realty_radar.config import settings

logger = logging.getLogger(__name__)

_redis_client: Any | None = None
_redis_initialized: bool = False


def get_redis_client() -> Any | None:
    """Redis 클라이언트 싱글톤 반환 (미설치 또는 연결 실패 시 None 반환)."""
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client

    _redis_initialized = True
    try:
        import redis

        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            db=settings.redis_db,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            decode_responses=True,
        )
        client.ping()
        _redis_client = client
        logger.info("Redis cache client connected successfully.")
    except Exception as exc:
        logger.warning("Redis client disabled or connection failed: %s", exc)
        _redis_client = None

    return _redis_client


class MapViewportCache:
    """지도 뷰포트 검색 결과를 Redis에 캐싱하는 매니저."""

    DEFAULT_TTL_SECONDS = 300  # 5분 캐시

    @classmethod
    def get_viewport_cache(cls, cache_key: str) -> dict[str, Any] | None:
        """Redis에서 뷰포트 캐시 데이터 조회."""
        client = get_redis_client()
        if client is None:
            return None

        try:
            cached_raw = client.get(f"map:viewport:{cache_key}")
            if cached_raw:
                return json.loads(cached_raw)
        except Exception as exc:
            logger.debug("Redis cache read error: %s", exc)
        return None

    @classmethod
    def set_viewport_cache(
        cls, cache_key: str, data: dict[str, Any], ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> None:
        """Redis에 뷰포트 캐시 데이터 저장."""
        client = get_redis_client()
        if client is None:
            return

        try:
            serialized = json.dumps(data, ensure_ascii=False)
            client.setex(f"map:viewport:{cache_key}", ttl_seconds, serialized)
        except Exception as exc:
            logger.debug("Redis cache write error: %s", exc)
