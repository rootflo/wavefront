from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, cast

import requests
from workflow_job.constants.auth import RootfloHeaders
from agents_module.services.workflow_inference_service import WorkflowInferenceService
from agents_module.utils.input_processing_utils import process_inference_inputs
from db_repo_module.cache.cache_manager import CacheManager
from flo_ai import BaseMessage
from flo_cloud.cloud_storage import CloudStorageManager
from flo_utils.streaming.event_message import BaseEventMessage
from flo_utils.streaming.message_processor import MessageProcessor, ProcessingResult
from flo_utils.constants.workflow import WorkflowStatus
from common_module.log.logger import logger

from .models import WorkflowEventMessage


class WorkflowMessageProcessor(MessageProcessor[ProcessingResult[Dict[str, Any]]]):
    def __init__(
        self,
        cloud_storage_manager: CloudStorageManager,
        cache_manager: CacheManager,
        workflow_inference_service: WorkflowInferenceService,
        floware_service_url: str,
        app_env: str = 'production',
        passthrough_secret: str | None = None,
    ):
        self.cloud_storage_manager = cloud_storage_manager
        self.cache_manager = cache_manager
        self.workflow_inference_service = workflow_inference_service
        self.floware_service_url = floware_service_url
        self.app_env = app_env
        self.passthrough_secret = passthrough_secret

    def _fetch_headers(self) -> dict[str, str]:
        """
        Fetch headers for HTTP requests to floware service.
        Adds passthrough authentication header for non-production environments.

        Returns:
            dict: Headers to include in HTTP requests
        """
        headers: dict[str, str] = {'Content-Type': 'application/json'}

        # Add passthrough header for non-production environments
        if self.app_env != 'production' and self.passthrough_secret:
            headers[RootfloHeaders.PASSTHROUGH] = self.passthrough_secret

        return headers

    async def process(self, message: BaseEventMessage) -> ProcessingResult:
        workflow_message = cast(WorkflowEventMessage, message)
        workflow_run_id = workflow_message.body['workflow_run_id']
        req_payload = {
            'workflow_run_id': workflow_run_id,
            'status': WorkflowStatus.IN_PROGRESS,
            'start_time': datetime.now().isoformat(),
        }

        response = self.__update_workflow_run_state(req_payload, workflow_run_id)
        if response.status_code != 200:
            logger.info(f'Failed to update workflow run state: {response.json()}')

        pipeline_job = workflow_message.body['pipeline_job']
        workflow_data = workflow_message.body['workflow_data']

        resolved_inputs = process_inference_inputs(pipeline_job['inputs'])
        inference_inputs: List[BaseMessage]
        if isinstance(resolved_inputs, list):
            inference_inputs = [cast(BaseMessage, item) for item in resolved_inputs]
        else:
            inference_inputs = [resolved_inputs]
        variables = pipeline_job['variables'] if pipeline_job['variables'] else {}

        (
            result,
            execution_time,
        ) = await self.workflow_inference_service.perform_inference_v2(
            workflow_data=workflow_data,
            variables=variables,
            inputs=inference_inputs,
            output_json_enabled=False,
        )

        return ProcessingResult(
            success=True,
            insights={
                'result': result,
                'execution_time': execution_time,
                'workflow_run_id': workflow_run_id,
            },
        )

    def store(
        self,
        insights: List[ProcessingResult[Dict[str, Any]]],
        is_failed: bool = False,
    ) -> bool:
        if not insights:
            logger.info('Insights is None, returning store False')
            return False
        result = insights[0]
        insights_payload = result.insights
        if not isinstance(insights_payload, dict):
            logger.info(f'Insights payload is not a dictionary for result: {result}')
            return False

        workflow_run_id = insights_payload.get('workflow_run_id')
        if not workflow_run_id:
            logger.info(f'Workflow run ID not found for result: {result}')
            return False

        req_payload = {
            'workflow_run_id': workflow_run_id,
            'end_time': datetime.now().isoformat(),
        }
        if result.success:
            req_payload['status'] = WorkflowStatus.COMPLETED
            req_payload['output'] = insights_payload.get('result')
        elif is_failed:
            req_payload['status'] = WorkflowStatus.FAILED
            req_payload['error'] = result.error if result.error else 'Unknown error'

        response = self.__update_workflow_run_state(req_payload, workflow_run_id)

        if response.status_code != 200:
            logger.info('Failed to update workflow run state')
            return False

        for result in insights:
            insights_payload = result.insights
            if not isinstance(insights_payload, dict):
                logger.info(
                    f'Insights payload is not a dictionary for result: {result}'
                )
                return False
            workflow_run_id: str | None = insights_payload.get('workflow_run_id')
            if not workflow_run_id:
                logger.info(f'Workflow run ID not found for result: {result}')
                return False

            req_payload: dict[str, Any] = {
                'workflow_run_id': workflow_run_id,
                'end_time': datetime.now().isoformat(),
            }
            if result.success:
                req_payload['status'] = WorkflowStatus.COMPLETED
                req_payload['output'] = (
                    insights_payload.get('result')
                    if insights_payload.get('result')
                    else None
                )
            elif is_failed:
                req_payload['status'] = WorkflowStatus.FAILED
                req_payload['error'] = result.error if result.error else 'Unknown error'

            response: requests.Response = self.__update_workflow_run_state(
                req_payload, workflow_run_id
            )
            if response.status_code != 200:
                logger.info(
                    f'Failed to update workflow run state for workflow run {workflow_run_id}: {response.json()}'
                )
                return False

        return True

    def __update_workflow_run_state(
        self, payload: dict[str, Any], workflow_run_id: str
    ) -> requests.Response:
        logger.info(f'Updating workflow run state for workflow run {workflow_run_id}')
        req_headers = self._fetch_headers()

        return requests.put(
            url=f'{self.floware_service_url}/v1/workflow-runs/{workflow_run_id}',
            headers=req_headers,
            json=payload,
        )
