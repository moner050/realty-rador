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


class RedisCacheService:
    """Redis 초고속 인메모리 캐싱 클라이언트 (.env 환경 변수 연동 & RESP2 구버전 HELLO 오류 해결)."""

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

        if not HAS_REDIS:
            logger.info("파이썬 redis 패키지가 설치되어 있지 않아 DB 다이렉트 조회가 수행됩니다.")
            return

        redis_host = host or settings.redis_host
        redis_port = port or settings.redis_port
        redis_pwd = password if password is not None else settings.redis_password
        redis_db_num = db if db is not None else settings.redis_db

        try:
            # protocol=2 옵션을 지정하여 구버전 Redis의 'unknown command HELLO' 에러 원천 차단
            conn_kwargs: dict[str, Any] = {
                "host": redis_host,
                "port": redis_port,
                "db": redis_db_num,
                "decode_responses": True,
                "socket_timeout": 1.5,
                "socket_connect_timeout": 1.5,
                "protocol": 2,  # RESP2 구버전/신버전 통합 호환 프로토콜
            }
            if redis_pwd:
                conn_kwargs["password"] = redis_pwd

            self._redis_client = redis.Redis(**conn_kwargs)
            # 연결 핑 테스트
            self._redis_client.ping()
            logger.info("Redis 서버 성공적 연결 완료 (host: %s, port: %d, db: %d)", redis_host, redis_port, redis_db_num)
        except Exception as e:
            logger.warning("Redis 서버 연결 실패 (DB 다이렉트 조회 폴백 가동): %s", e)
            self._redis_client = None

    def get(self, key: str) -> Any | None:
        """Redis에서 키로 데이터 조회."""
        if not self._redis_client:
            return None
        try:
            val = self._redis_client.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.debug("Redis GET 예외 (key: %s): %s", key, e)
        return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Redis에 데이터 적재 (기본 TTL: 300초)."""
        if not self._redis_client:
            return False
        try:
            expire_sec = ttl if ttl is not None else self.default_ttl
            serialized = json.dumps(value, default=str, ensure_ascii=False)
            self._redis_client.set(key, serialized, ex=expire_sec)
            return True
        except Exception as e:
            logger.debug("Redis SET 예외 (key: %s): %s", key, e)
            return False

    def delete_pattern(self, pattern: str) -> int:
        """패턴에 일치하는 캐시 키 일괄 삭제 (캐시 무효화)."""
        if not self._redis_client:
            return 0
        try:
            keys = self._redis_client.keys(pattern)
            if keys:
                return self._redis_client.delete(*keys)
        except Exception as e:
            logger.debug("Redis DELETE 예외 (pattern: %s): %s", pattern, e)
        return 0


# 전역 단일 Redis 캐시 인스턴스
redis_cache = RedisCacheService()
