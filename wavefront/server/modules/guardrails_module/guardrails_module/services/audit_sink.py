"""Durable record of guardrail decisions."""

from typing import Any

from common_module.log.logger import logger


class DatabaseAuditSink:
    """Persists every guardrail decision, implementing flo_ai's AuditSink port.

    Writes findings only - adapter, finding code, severity, entity counts -
    never the evaluated content or the matched values. A guardrail exists to
    stop sensitive payloads spreading; an audit table that copies them into a
    second, longer-lived store would defeat the point of the feature.
    """

    def __init__(self, guardrail_audit_repository: Any):
        self.guardrail_audit_repository = guardrail_audit_repository

    async def record(self, decision: Any, context: Any) -> None:
        """Write one row per evaluation.

        Never raises. A decision has already been enforced by the time this
        runs, so failing here would turn a logging problem into a failed
        request - and on the fail-closed paths, into a namespace outage. The
        ERROR log is the signal that the trail has gaps.
        """
        try:
            findings = [
                {
                    'adapter': result.adapter,
                    'status': result.status.value,
                    'action': result.action.value,
                    'finding_code': result.finding_code,
                    'message': result.message,
                    'severity': result.severity,
                    'failure_class': result.failure_class.value,
                    'metadata': result.provider_metadata or {},
                }
                for result in decision.results
            ]

            await self.guardrail_audit_repository.create(
                namespace=context.namespace or 'unknown',
                agent_id=context.agent_id,
                user_id=context.user_id,
                run_id=context.run_id,
                stage=context.workflow_stage.value,
                action=decision.action.value,
                observed_action=decision.observed_action.value,
                enforced=decision.enforced,
                # The column alerting watches. An adapter erroring means the
                # check did not run, whatever the final action was - and under
                # fail-open that final action is ALLOW, indistinguishable from
                # genuinely clean traffic without this flag.
                had_error=any(result.is_error for result in decision.results),
                policy_version=decision.policy_version,
                findings=findings,
            )
        except Exception as exc:
            logger.error(f'Failed to write guardrail audit event: {exc}', exc_info=exc)
