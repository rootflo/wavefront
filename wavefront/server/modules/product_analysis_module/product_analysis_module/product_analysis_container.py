from dependency_injector import containers
from dependency_injector import providers
from product_analysis_module.product_analysis_service import ProductAnalysisService


class ProductAnalysisContainer(containers.DeclarativeContainer):
    product_analysis_service = providers.Singleton(ProductAnalysisService)
