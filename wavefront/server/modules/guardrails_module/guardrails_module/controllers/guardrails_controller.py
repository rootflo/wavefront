import asyncio

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import JSONResponse
from guardrails_module.container import GuardrailsContainer
from guardrails_module.models.schemas import (
    PII_ADAPTER,
    SUPPORTED_ADAPTERS,
    PiiPreviewPayload,
    PolicyPreviewPayload,
    UpdateGuardrailPolicyPayload,
)
from guardrails_module.services.guardrails_service import (
    GuardrailsService,
    build_resolved_policy,
)
from user_management_module.utils.user_utils import check_is_admin

guardrails_router = APIRouter()


async def _require_admin(request: Request, response_formatter: ResponseFormatter):
    """Guardrail policy is a security control, so reads are admin-only too.

    Its contents disclose exactly which checks are running and at what
    thresholds, which is a map of how to get past them.
    """
    role_id = request.state.session.role_id
    if not await check_is_admin(role_id):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Admin access required to manage guardrail policies'
            ),
        )
    return None


@guardrails_router.get('/v1/guardrails/adapters')
@inject
async def list_supported_adapters(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    guardrails_engine=Depends(Provide[GuardrailsContainer.guardrails_engine]),
):
    """Adapters this deployment can actually run.

    Reports what the engine registered at startup, not a static list. A policy
    naming an adapter that failed to construct — Presidio without its optional
    dependency, Azure without credentials — is treated as a misconfiguration
    and fails closed, so offering an unavailable provider in the UI would let
    an admin block all traffic for their namespace in one click.
    """
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    available = list(getattr(guardrails_engine, 'registered', ()) or ())
    unavailable = [name for name in SUPPORTED_ADAPTERS if name not in available]
    if unavailable:
        logger.warning(
            f'Guardrail adapters known but not available on this deployment: '
            f'{", ".join(unavailable)}'
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'adapters': available, 'unavailable': unavailable}
        ),
    )


def _pii_adapter(guardrails_engine):
    """The registered Presidio adapter, or None on a deployment without it."""
    getter = getattr(guardrails_engine, 'get_adapter', None)
    if getter is None:  # pragma: no cover - older flo_ai release
        return None
    return getter(PII_ADAPTER)


@guardrails_router.get('/v1/guardrails/pii/entities')
@inject
async def list_pii_entities(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    guardrails_engine=Depends(Provide[GuardrailsContainer.guardrails_engine]),
):
    """Entity types this deployment can actually detect, grouped for display.

    Availability is read from the running analyzer rather than from a constant.
    Presidio ships far more recognisers than it loads by default, and the set
    depends on which optional ones started successfully — so a static list
    would offer checkboxes that detect nothing, and selecting one fails the
    namespace closed.
    """
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    adapter = _pii_adapter(guardrails_engine)
    if adapter is None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'groups': [], 'available': False}
            ),
        )

    try:
        from flo_ai.guardrails.adapters.pii_catalog import describe, group_sort_key
        from flo_ai.guardrails.adapters.presidio_adapter import DEFAULT_ENTITIES

        entities = await adapter.supported_entities()
        precision = await adapter.entity_precision()

        grouped: dict = {}
        for entity_id in entities:
            meta = describe(entity_id)
            detail = precision.get(entity_id) or {}
            grouped.setdefault(meta.group, []).append(
                {
                    'id': entity_id,
                    'label': meta.label,
                    'description': meta.description,
                    'country_code': meta.country_code,
                    'example': meta.example,
                    'precision': detail.get('precision', 'pattern'),
                    'min_pattern_score': detail.get('min_pattern_score'),
                    'default_selected': entity_id in DEFAULT_ENTITIES,
                }
            )

        groups = [
            {
                'group': group,
                'country_code': items[0]['country_code'],
                'entities': sorted(items, key=lambda item: item['label']),
            }
            for group, items in sorted(
                grouped.items(), key=lambda pair: group_sort_key(pair[0])
            )
        ]
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'groups': groups, 'available': True}
            ),
        )
    except Exception as e:
        logger.error(f'Failed to list PII entity types: {e}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


@guardrails_router.post('/v1/guardrails/pii/preview')
@inject
async def preview_pii_policy(
    request: Request,
    payload: PiiPreviewPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    guardrails_engine=Depends(Provide[GuardrailsContainer.guardrails_engine]),
):
    """Show what a draft PII policy would do to sample text.

    Nothing is persisted and no stored policy is read, so this is safe to call
    against settings the admin has not saved yet. Match offsets are returned so
    the console can highlight spans; the matched values themselves are not,
    keeping the adapter's "types and counts, never values" rule intact even
    though the admin supplied the text.
    """
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    adapter = _pii_adapter(guardrails_engine)
    if adapter is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'The PII provider is not available on this deployment.'
            ),
        )

    try:
        # Bounded independently of any policy timeout: this runs admin-supplied
        # configuration over admin-supplied text and must not pin a worker.
        result = await asyncio.wait_for(
            adapter.preview(payload.text, payload.options), timeout=15
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'result': result}),
        )
    except asyncio.TimeoutError:
        logger.warning('PII preview timed out')
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=response_formatter.buildErrorResponse(
                'Preview timed out. Narrow the selected entity types or '
                'shorten the sample text.'
            ),
        )
    except Exception as e:
        logger.error(f'PII preview failed: {e}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


def _serialise_decision(decision, stage: str) -> dict:
    """Flatten a PolicyDecision for the console.

    Adapter messages and finding codes are included deliberately. They are
    operator detail withheld from end users at enforcement time, but this
    endpoint is admin-only and the whole point is to explain *why* a policy
    reached its verdict.
    """
    return {
        'stage': stage,
        'action': decision.action.value,
        'observed_action': decision.observed_action.value,
        'enforced': decision.enforced,
        'transformed_text': decision.transformed_content,
        'results': [
            {
                'adapter': result.adapter,
                'status': result.status.value,
                'action': result.action.value,
                'finding_code': result.finding_code,
                'message': result.message,
                'severity': result.severity,
                'failure_class': result.failure_class.value,
                'metadata': result.provider_metadata,
            }
            for result in decision.results
        ],
    }


@guardrails_router.post('/v1/guardrails/policies/preview')
@inject
async def preview_guardrail_policy(
    request: Request,
    payload: PolicyPreviewPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    guardrails_engine=Depends(Provide[GuardrailsContainer.guardrails_engine]),
):
    """Show what an unsaved policy would do to sample text, at both stages.

    Runs the draft through the same engine, adapters and composition rules that
    enforcement uses, so the verdict shown is the verdict that would happen.

    Unlike ``PUT``, this does **not** reject a policy naming an unavailable
    provider. That combination fails closed and blocks every request in the
    namespace, and seeing exactly that here - before saving - is the reason the
    endpoint exists.

    Nothing is persisted and no stored policy is read or written.
    """
    from flo_ai.guardrails import Principal, WorkflowStage
    from flo_ai.guardrails.contracts import DISABLED_POLICY

    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    try:
        if payload.is_enabled:
            policy = build_resolved_policy(
                mode=payload.mode.value,
                adapter_entries=[
                    {
                        'name': adapter.name,
                        'stages': [stage.value for stage in adapter.stages],
                        'on_error': adapter.on_error.value,
                        'timeout_seconds': adapter.timeout_seconds,
                        'options': adapter.options,
                    }
                    for adapter in payload.adapters
                ],
                describe='policy preview',
            )
        else:
            # Master switch off is a real outcome to preview, not an error:
            # it is the answer to "what happens if I turn this off?".
            policy = DISABLED_POLICY

        principal = Principal(namespace='__preview__')

        async def run(stage):
            return await guardrails_engine.preview(
                payload.text, principal, stage, policy
            )

        # Bounded independently of the per-adapter timeouts in the draft, which
        # an admin can set as high as 60s each. A preview must not pin a worker.
        stages = await asyncio.wait_for(
            asyncio.gather(
                run(WorkflowStage.BEFORE_MODEL), run(WorkflowStage.AFTER_MODEL)
            ),
            timeout=30,
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'stages': [
                        _serialise_decision(stages[0], 'BEFORE_MODEL'),
                        _serialise_decision(stages[1], 'AFTER_MODEL'),
                    ]
                }
            ),
        )
    except asyncio.TimeoutError:
        logger.warning('Policy preview timed out')
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=response_formatter.buildErrorResponse(
                'Preview timed out. A configured provider is not responding.'
            ),
        )
    except Exception as e:
        # The text is admin-supplied and may contain real PII, so it is never
        # logged - only the failure.
        logger.error(f'Policy preview failed: {e}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


@guardrails_router.get('/v1/guardrails/policies')
@inject
async def list_guardrail_policies(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    guardrails_service: GuardrailsService = Depends(
        Provide[GuardrailsContainer.guardrails_service]
    ),
):
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    try:
        policies = await guardrails_service.list_policies()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'policies': [
                        guardrails_service.to_response(policy) for policy in policies
                    ]
                }
            ),
        )
    except Exception as e:
        logger.error(f'Failed to list guardrail policies: {e}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


@guardrails_router.get('/v1/guardrails/policies/{namespace}')
@inject
async def get_guardrail_policy(
    request: Request,
    namespace: str = Path(..., description='The namespace the policy applies to'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    guardrails_service: GuardrailsService = Depends(
        Provide[GuardrailsContainer.guardrails_service]
    ),
):
    """A namespace with no policy row returns the disabled default, not a 404.

    The UI needs something to render either way, and "no policy" and "policy
    that is switched off" are the same state as far as enforcement goes.
    """
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    try:
        policy = await guardrails_service.get_policy_response(namespace)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'policy': policy}),
        )
    except Exception as e:
        logger.error(f'Failed to fetch guardrail policy for {namespace}: {e}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


@guardrails_router.put('/v1/guardrails/policies/{namespace}')
@inject
async def update_guardrail_policy(
    request: Request,
    payload: UpdateGuardrailPolicyPayload,
    namespace: str = Path(..., description='The namespace the policy applies to'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    guardrails_service: GuardrailsService = Depends(
        Provide[GuardrailsContainer.guardrails_service]
    ),
    guardrails_engine=Depends(Provide[GuardrailsContainer.guardrails_engine]),
):
    """Create or replace a namespace's policy, including the master switch."""
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    # Reject adapters this deployment cannot run, rather than storing them and
    # failing closed on every subsequent request.
    #
    # An unregistered adapter is a MISCONFIGURED result, which is always
    # fail-closed by design, so accepting one here lets an admin block every
    # request in their namespace by saving a policy. The schema can only check
    # the name against the list of adapters that exist in principle; whether
    # one is actually loaded is a property of the running engine.
    available = set(getattr(guardrails_engine, 'registered', ()) or ())
    missing = [a.name for a in payload.adapters if a.name not in available]
    if missing:
        logger.warning(
            f'Rejected guardrail policy for {namespace} naming unavailable '
            f'adapters: {", ".join(missing)}'
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'These safety providers are not available on this deployment: '
                f'{", ".join(missing)}. Available: '
                f'{", ".join(sorted(available)) or "none"}.'
            ),
        )

    try:
        policy = await guardrails_service.update_policy(
            namespace=namespace,
            is_enabled=payload.is_enabled,
            mode=payload.mode.value,
            adapters=[
                {
                    'name': adapter.name,
                    'stages': [stage.value for stage in adapter.stages],
                    'on_error': adapter.on_error.value,
                    'timeout_seconds': adapter.timeout_seconds,
                    'options': adapter.options,
                }
                for adapter in payload.adapters
            ],
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'Guardrail policy updated successfully',
                    'policy': guardrails_service.to_response(policy),
                }
            ),
        )
    except Exception as e:
        logger.error(f'Failed to update guardrail policy for {namespace}: {e}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


@guardrails_router.delete('/v1/guardrails/policies/{namespace}')
@inject
async def delete_guardrail_policy(
    request: Request,
    namespace: str = Path(..., description='The namespace the policy applies to'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    guardrails_service: GuardrailsService = Depends(
        Provide[GuardrailsContainer.guardrails_service]
    ),
):
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    try:
        await guardrails_service.delete_policy(namespace)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'Guardrail policy deleted successfully'}
            ),
        )
    except Exception as e:
        logger.error(f'Failed to delete guardrail policy for {namespace}: {e}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )
