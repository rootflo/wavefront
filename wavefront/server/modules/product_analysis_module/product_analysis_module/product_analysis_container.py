from dependency_injector import containers
from dependency_injector import providers

from product_analysis_module.product_analysis_service import ProductAnalysisService


def _excluded_emails(raw: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in (raw or '').split(',') if part.strip())


class ProductAnalysisContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    product_analysis_service = providers.Singleton(
        ProductAnalysisService,
        excluded_emails=providers.Callable(
            _excluded_emails, config.product_analysis.excluded_emails
        ),
    )
