from db_repo_module.models.guardrail_audit_event import GuardrailAuditEvent
from db_repo_module.models.guardrail_policy import GuardrailPolicy
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector import containers
from dependency_injector import providers
from guardrails_module.services.audit_sink import DatabaseAuditSink
from guardrails_module.services.engine_factory import build_guardrails_engine
from guardrails_module.services.guardrails_service import (
    DatabasePolicyResolver,
    GuardrailsService,
)


class GuardrailsContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    # External dependencies
    db_client = providers.Dependency()
    cache_manager = providers.Dependency()

    # Repository
    guardrail_policy_repository = providers.Singleton(
        SQLAlchemyRepository[GuardrailPolicy],
        model=GuardrailPolicy,
        db_client=db_client,
    )

    guardrail_audit_repository = providers.Singleton(
        SQLAlchemyRepository[GuardrailAuditEvent],
        model=GuardrailAuditEvent,
        db_client=db_client,
    )

    # Services
    guardrails_service = providers.Singleton(
        GuardrailsService,
        guardrail_policy_repository=guardrail_policy_repository,
        cache_manager=cache_manager,
    )

    # Bridges the stored policy into flo_ai's PolicyResolver port, so the SDK
    # never depends on Postgres or Redis directly.
    policy_resolver = providers.Singleton(
        DatabasePolicyResolver,
        guardrails_service=guardrails_service,
    )

    # Durable record of every decision. Also what makes fail-open defensible:
    # an adapter outage downgrades to ALLOW, and the had_error rate is the only
    # way to tell that apart from traffic that was genuinely clean.
    audit_sink = providers.Singleton(
        DatabaseAuditSink,
        guardrail_audit_repository=guardrail_audit_repository,
    )

    # One engine per process. Adapters hold expensive state — a spaCy model and
    # an HTTP connection pool — so they must not be rebuilt per request.
    #
    # The cache manager backs the shared tier of the verdict cache, which holds
    # only content-free verdicts: Azure allows and blocks, never Presidio's
    # redactions. Sharing those is what stops a freshly started worker paying a
    # provider again for a conversation an older one already checked.
    guardrails_engine = providers.Singleton(
        build_guardrails_engine,
        policy_resolver=policy_resolver,
        audit_sink=audit_sink,
        cache_manager=cache_manager,
    )
