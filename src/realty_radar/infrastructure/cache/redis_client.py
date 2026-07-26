import time
import json
import logging
from typing import Any

from realty_radar.config import settings

try:
    import redis
    HAS_REDIS = True
except ImportError:
    redis = None
    HAS_REDIS = False

logger = logging.getLogger(__name__)


class InMemoryCache:
    """Redis 미사용/연결 실패 시 자동 대체되는 파이썬 인메모리 캐시 (TTL 자동 만료 지원)."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        if key not in self._store:
            return None
        val, expire_at = self._store[key]
        if time.time() > expire_at:
            del self._store[key]
            return None
        return val

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        expire_at = time.time() + ttl
        self._store[key] = (value, expire_at)
        return True

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def delete_pattern(self, pattern: str) -> int:
        import fnmatch
        keys_to_del = [k for k in self._store.keys() if fnmatch.fnmatch(k, pattern)]
        for k in keys_to_del:
            del self._store[k]
        return len(keys_to_del)


class RedisCacheService:
    """Redis 인메모리 캐싱 클라이언트 (Redis 미사용 시 로컬 메모리 캐시 100% 하이브리드 지원)."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        db: int | None = None,
        default_ttl: int = 300,
    ):
        self.default_ttl = default_ttl
        self._redis_client = None
        self._memory_cache = InMemoryCache()

        if not HAS_REDIS:
            logger.info("파이썬 redis 패키지가 설치되어 있지 않아 로컬 인메모리 캐시가 가동됩니다.")
            return

        redis_host = host or settings.redis_host
        redis_port = port or settings.redis_port
        redis_pwd = password if password is not None else settings.redis_password
        redis_db_num = db if db is not None else settings.redis_db

        try:
            conn_kwargs: dict[str, Any] = {
                "host": redis_host,
                "port": redis_port,
                "db": redis_db_num,
                "decode_responses": True,
                "socket_timeout": 1.0,
                "socket_connect_timeout": 1.0,
                "protocol": 2,
            }
            if redis_pwd:
                conn_kwargs["password"] = redis_pwd

            self._redis_client = redis.Redis(**conn_kwargs)
            self._redis_client.ping()
            logger.info("Redis 서버 성공적 연결 완료 (host: %s, port: %d)", redis_host, redis_port)
        except Exception as e:
            logger.info("Redis 서버 미사용/연결 미동작 -> 파이썬 로컬 인메모리 캐시 모드로 전환됩니다.")
            self._redis_client = None

    def get(self, key: str) -> Any | None:
        """캐시에서 데이터 조회 (Redis 미사용 시 로컬 인메모리 조율)."""
        if not self._redis_client:
            return self._memory_cache.get(key)
        try:
            val = self._redis_client.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.debug("Redis GET 예외 -> 인메모리 폴백: %s", e)
            return self._memory_cache.get(key)
        return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """캐시에 데이터 적재."""
        expire_sec = ttl if ttl is not None else self.default_ttl
        self._memory_cache.set(key, value, ttl=expire_sec)

        if not self._redis_client:
            return True
        try:
            serialized = json.dumps(value, default=str, ensure_ascii=False)
            self._redis_client.set(key, serialized, ex=expire_sec)
            return True
        except Exception as e:
            logger.debug("Redis SET 예외: %s", e)
            return True

    def delete(self, key: str) -> bool:
        """특정 키 삭제."""
        self._memory_cache.delete(key)
        if not self._redis_client:
            return True
        try:
            self._redis_client.delete(key)
            return True
        except Exception:
            return True

    def delete_pattern(self, pattern: str) -> int:
        """패턴 삭제."""
        mem_deleted = self._memory_cache.delete_pattern(pattern)
        if not self._redis_client:
            return mem_deleted
        try:
            keys = self._redis_client.keys(pattern)
            if keys:
                return self._redis_client.delete(*keys)
        except Exception:
            pass
        return mem_deleted


# 전역 단일 통합 캐시 서비스 인스턴스 (Redis 미설치/미사용 시 로컬 인메모리 100% 자동 가동)
cache_service = RedisCacheService()
redis_cache = cache_service
