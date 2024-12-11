import json
from typing import Any, Dict, Optional
from datetime import datetime
from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler
from langchain.schema.agent import AgentAction, AgentFinish
from langchain.schema import HumanMessage, AIMessage, BaseMessage
from langchain_core.prompts.chat import ChatPromptValue
from flo_ai.storage.data_collector import DataCollector
from flo_ai.common.flo_logger import get_logger


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (HumanMessage, AIMessage, BaseMessage)):
            return {
                'type': obj.__class__.__name__,
                'content': obj.content,
                'additional_kwargs': obj.additional_kwargs,
            }
        elif isinstance(obj, AgentAction):
            return {
                'type': 'AgentAction',
                'tool': obj.tool,
                'tool_input': obj.tool_input,
                'log': obj.log,
            }
        elif isinstance(obj, AgentFinish):
            return {
                'type': 'AgentFinish',
                'return_values': obj.return_values,
                'log': obj.log,
            }
        elif isinstance(obj, ChatPromptValue):
            return {
                'type': 'ChatPromptValue',
                'messages': [self.default(msg) for msg in obj.messages],
            }
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, UUID):
            return str(obj)
        elif hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return super().default(obj)


class FloExecutionLogger(BaseCallbackHandler):
    def __init__(self, data_collector: DataCollector):
        self.data_collector = data_collector
        self.runs = {}
        self.encoder = EnhancedJSONEncoder()

    def _encode_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        return json.loads(self.encoder.encode(entry))

    def _store_entry(self, entry: Dict[str, Any]) -> None:
        try:
            encoded_entry = self._encode_entry(entry)
            self.data_collector.store_entry(encoded_entry)
        except Exception as e:
            get_logger().error(f'Error storing entry in FloExecutionLogger: {e}')

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        chain_name = (
            serialized.get('name', 'unnamed_chain') if serialized else 'unnamed_chain'
        )
        self.runs[str(run_id)] = {
            'type': 'chain',
            'start_time': datetime.utcnow(),
            'inputs': inputs,
            'name': chain_name,
            'parent_run_id': str(parent_run_id) if parent_run_id else None,
        }

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if str(run_id) in self.runs:
            run_info = self.runs[str(run_id)]
            run_info['end_time'] = datetime.utcnow()
            run_info['outputs'] = outputs
            run_info['status'] = 'completed'
            self._store_entry(run_info)
            del self.runs[str(run_id)]

    def on_chain_error(
        self,
        error: Exception,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if str(run_id) in self.runs:
            run_info = self.runs[str(run_id)]
            run_info['end_time'] = datetime.utcnow()
            run_info['error'] = str(error)
            run_info['status'] = 'error'
            self._store_entry(run_info)
            del self.runs[str(run_id)]

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        self.runs[str(run_id)] = {
            'type': 'tool',
            'start_time': datetime.utcnow(),
            'tool_name': serialized.get('name', 'unnamed_tool'),
            'input': input_str,
            'parent_run_id': str(parent_run_id) if parent_run_id else None,
        }

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if str(run_id) in self.runs:
            run_info = self.runs[str(run_id)]
            run_info['end_time'] = datetime.utcnow()
            run_info['output'] = output
            run_info['status'] = 'completed'
            self._store_entry(run_info)
            del self.runs[str(run_id)]

    def on_tool_error(
        self,
        error: Exception,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        if str(run_id) in self.runs:
            run_info = self.runs[str(run_id)]
            run_info['end_time'] = datetime.utcnow()
            run_info['error'] = str(error)
            run_info['status'] = 'error'
            self._store_entry(run_info)
            del self.runs[str(run_id)]

    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        agent_info = {
            'type': 'agent_action',
            'start_time': datetime.utcnow(),
            'tool': action.tool,
            'tool_input': action.tool_input,
            'log': action.log,
            'parent_run_id': str(parent_run_id) if parent_run_id else None,
        }
        self.runs[str(run_id)] = agent_info
        self._store_entry(agent_info)

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        log_entry = {
            'type': 'agent_finish',
            'time': datetime.utcnow(),
            'output': finish.return_values,
            'log': finish.log,
            'parent_run_id': str(parent_run_id) if parent_run_id else None,
        }
        self._store_entry(log_entry)
