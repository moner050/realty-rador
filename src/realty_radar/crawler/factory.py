from realty_radar.crawler.adapters.site_a.adapter import SiteAAdapter
from realty_radar.crawler.adapters.site_b.adapter import SiteBAdapter
from realty_radar.crawler.base.adapter import ListingSourceAdapter
from realty_radar.crawler.base.exceptions import AdapterNotFoundException


class AdapterFactory:
    """사이트 소스 코드에 따라 수집 어댑터를 동적 생성하는 팩토리."""

    @staticmethod
    def get_adapter(source_code: str) -> ListingSourceAdapter:
        """소소 코드 기반 어댑터 인스턴스 반환."""
        code_upper = source_code.upper()

        if code_upper == "SITE_A":
            return SiteAAdapter()
        elif code_upper == "SITE_B":
            return SiteBAdapter()
        else:
            raise AdapterNotFoundException(f"등록되지 않은 소스 코드 어댑터입니다: {source_code}")
