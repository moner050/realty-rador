class CrawlException(Exception):
    """크롤링 최상위 예외 클래스."""

    pass


class SessionExpiredException(CrawlException):
    """로그인 세션 만료 예외."""

    pass


class CaptchaBlockedException(CrawlException):
    """CAPTCHA 또는 차단 페이지 감지 예외."""

    pass


class RateLimitExceededException(CrawlException):
    """요청 제한 초과 예외."""

    pass


class ParseException(CrawlException):
    """HTML 파싱 오류 예외."""

    pass


class AdapterNotFoundException(CrawlException):
    """사이트 어댑터 미존재 예외."""

    pass
