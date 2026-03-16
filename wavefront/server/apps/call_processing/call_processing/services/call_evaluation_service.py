"""
Post-call evaluation metrics service

Emits a `call.evaluation` OTel span with:
  - Quantitative metrics: turn counts, interruptions, tool calls, language switches, word counts
  - Qualitative LLM analysis: multi-dimensional rubric scoring via Azure OpenAI (optional)

LLM analysis is best-effort — if Azure config is missing or the call fails, the metrics
span is still emitted with eval.llm_analysis_skipped=True.

Required env vars for LLM analysis (all must be set to enable):
  CALL_EVAL_AZURE_ENDPOINT    e.g. https://my-resource.openai.azure.com
  CALL_EVAL_AZURE_API_KEY
  CALL_EVAL_AZURE_LLM_MODEL   (optional, default: gpt-4.1)
  CALL_EVAL_AZURE_API_VERSION (optional, default: 2024-02-01)
"""

import json
import os
from typing import Any, Dict, List, Optional

import aiohttp
from call_processing.log.logger import logger
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

_EVAL_DIMENSIONS = [
    'goal_completion',
    'instruction_adherence',
    'tone_professionalism',
    'naturalness',
    'conciseness',
    'handling_unknowns',
    'language_quality',
]


class CallEvaluationService:
    """Emits a post-call OTel span with quantitative metrics and optional LLM analysis."""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    @staticmethod
    async def record_call_metrics(
        call_id: str,
        agent_config: Dict[str, Any],
        call_outcome: str,
        transcript_log: List[Dict[str, Any]],
        stats: Dict[str, Any],
    ) -> None:
        """
        Record call evaluation metrics as an OTel span.

        Args:
            call_id: Unique call identifier
            agent_config: Voice agent configuration (id, name, system_prompt, etc.)
            call_outcome: "completed" | "cancelled" | "error" | "stopped"
            transcript_log: List of {"role", "content", "timestamp"} dicts
            stats: Dict with keys: user_turns, assistant_turns, interruption_count,
                   tool_calls_count, language_switch_count
        """
        try:
            agent_id = str(agent_config.get('id', ''))
            agent_name = agent_config.get('name', '')

            user_turns = stats.get('user_turns', 0)
            assistant_turns = stats.get('assistant_turns', 0)
            total_turns = user_turns + assistant_turns

            total_words_user = sum(
                len(t['content'].split())
                for t in transcript_log
                if t.get('role') == 'user' and t.get('content')
            )
            total_words_assistant = sum(
                len(t['content'].split())
                for t in transcript_log
                if t.get('role') == 'assistant' and t.get('content')
            )

            logger.info(
                f'Recording call evaluation for {call_id}: outcome={call_outcome}, '
                f'turns={total_turns}, user_words={total_words_user}, '
                f'assistant_words={total_words_assistant}'
            )

            with tracer.start_as_current_span(
                'call.evaluation',
                attributes={
                    'call.id': call_id,
                    'voice_agent.id': agent_id,
                    'voice_agent.name': agent_name,
                    # --- Call outcome ---
                    'call.outcome': call_outcome,
                    # --- Turn counts ---
                    'call.total_turns': total_turns,
                    'call.user_turns': user_turns,
                    'call.assistant_turns': assistant_turns,
                    # --- Engagement metrics ---
                    'call.interruption_count': stats.get('interruption_count', 0),
                    'call.tool_calls_count': stats.get('tool_calls_count', 0),
                    'call.language_switch_count': stats.get('language_switch_count', 0),
                    # --- Transcript volume ---
                    'call.transcript_turns': len(transcript_log),
                    'call.total_words_user': total_words_user,
                    'call.total_words_assistant': total_words_assistant,
                },
            ) as span:
                # Add one span event per turn for searchable transcript
                for entry in transcript_log:
                    content = entry.get('content', '')
                    span.add_event(
                        'turn',
                        {
                            'role': entry.get('role', ''),
                            'content': content,
                            'timestamp': entry.get('timestamp', ''),
                            'word_count': len(content.split()) if content else 0,
                        },
                    )

                # --- LLM qualitative analysis (best-effort) ---
                azure_config = CallEvaluationService._get_azure_eval_config()
                if azure_config and transcript_log:
                    try:
                        prompt = CallEvaluationService._build_eval_prompt(
                            system_prompt=agent_config.get('system_prompt', ''),
                            transcript_log=transcript_log,
                        )
                        analysis = await CallEvaluationService._call_azure_llm(
                            prompt, azure_config
                        )
                        CallEvaluationService._apply_analysis_to_span(span, analysis)
                        logger.info(
                            f"LLM analysis complete for {call_id}: "
                            f"overall_rating={analysis.get('overall_rating')}"
                        )
                    except Exception as e:
                        logger.error(
                            f'LLM analysis failed for {call_id}: {e}', exc_info=True
                        )
                        span.set_attribute('eval.llm_analysis_skipped', True)
                else:
                    reason = (
                        'no Azure config' if not azure_config else 'empty transcript'
                    )
                    logger.info(f'LLM eval skipped for {call_id}: {reason}')
                    span.set_attribute('eval.llm_analysis_skipped', True)

        except Exception as e:
            logger.error(
                f'Error recording call evaluation for {call_id}: {e}', exc_info=True
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_azure_eval_config() -> Optional[Dict[str, str]]:
        """Read Azure OpenAI eval config from env vars. Returns None if incomplete."""
        endpoint = os.getenv('CALL_EVAL_AZURE_ENDPOINT', '').rstrip('/')
        api_key = os.getenv('CALL_EVAL_AZURE_API_KEY', '')
        llm_model = os.getenv('CALL_EVAL_AZURE_LLM_MODEL', 'gpt-4.1')
        api_version = os.getenv('CALL_EVAL_AZURE_API_VERSION', '2025-01-01-preview')

        if not all([endpoint, api_key]):
            return None

        return {
            'endpoint': endpoint,
            'api_key': api_key,
            'llm_model': llm_model,
            'api_version': api_version,
        }

    @staticmethod
    def _build_eval_prompt(
        system_prompt: str, transcript_log: List[Dict[str, Any]]
    ) -> str:
        """Build the evaluation prompt with rubric and transcript."""
        transcript_text = '\n'.join(
            f"{entry['role'].upper()}: {entry.get('content', '')}"
            for entry in transcript_log
            if entry.get('content', '').strip()
        )

        return f"""You are an expert AI quality assurance evaluator for voice agent conversations.
Evaluate the transcript below against the agent's configured objective.

## Agent Objective (System Prompt)
{system_prompt}

## Transcript
{transcript_text}

## Evaluation Rubric
Score each dimension from 1 (very poor) to 10 (excellent). Include a brief comment (1-2 sentences).

Dimensions:
- goal_completion: Did the agent achieve the conversation's objective as defined in the system prompt?
- instruction_adherence: Did the agent follow all rules, restrictions, persona and format instructions in the system prompt?
- tone_professionalism: Was the tone warm, professional and appropriate to the context?
- naturalness: Did the conversation flow naturally, avoiding robotic, repetitive or scripted-sounding phrasing?
- conciseness: Were responses appropriately brief without sacrificing clarity? Penalise over-verbose responses.
- handling_unknowns: Did the agent gracefully handle questions outside its scope — avoiding hallucination and staying in persona?
- language_quality: Clarity, grammar and vocabulary appropriateness. For multi-language calls, assess the switched language too.

## Output Format
Respond ONLY with a valid JSON object in this exact structure:
{{
  "overall_rating": <int 1-10>,
  "summary": "<2-3 sentence summary of the conversation>",
  "dimensions": {{
    "goal_completion":       {{"score": <int>, "comment": "<str>"}},
    "instruction_adherence": {{"score": <int>, "comment": "<str>"}},
    "tone_professionalism":  {{"score": <int>, "comment": "<str>"}},
    "naturalness":           {{"score": <int>, "comment": "<str>"}},
    "conciseness":           {{"score": <int>, "comment": "<str>"}},
    "handling_unknowns":     {{"score": <int>, "comment": "<str>"}},
    "language_quality":      {{"score": <int>, "comment": "<str>"}}
  }},
  "strengths": ["<str>", ...],
  "improvement_areas": ["<str>", ...]
}}"""

    @staticmethod
    async def _call_azure_llm(prompt: str, config: Dict[str, str]) -> Dict[str, Any]:
        """POST to Azure OpenAI and return parsed JSON result."""
        url = (
            f"{config['endpoint']}/openai/deployments/{config['llm_model']}"
            f"/chat/completions?api-version={config['api_version']}"
        )
        headers = {
            'api-key': config['api_key'],
            'Content-Type': 'application/json',
        }
        payload = {
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.1,
            'response_format': {'type': 'json_object'},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f'Azure LLM returned {resp.status}: {body[:200]}'
                    )
                data = await resp.json()
                content = data['choices'][0]['message']['content']
                return json.loads(content)

    @staticmethod
    def _apply_analysis_to_span(span: Any, analysis: Dict[str, Any]) -> None:
        """Write LLM analysis result as OTel span attributes."""
        span.set_attribute('eval.llm_analysis_skipped', False)
        span.set_attribute(
            'eval.overall_rating', int(analysis.get('overall_rating', 0))
        )
        span.set_attribute('eval.summary', str(analysis.get('summary', '')))

        dimensions = analysis.get('dimensions', {})
        for dim in _EVAL_DIMENSIONS:
            dim_data = dimensions.get(dim, {})
            span.set_attribute(f'eval.{dim}', int(dim_data.get('score', 0)))
            span.set_attribute(f'eval.{dim}_comment', str(dim_data.get('comment', '')))

        span.set_attribute(
            'eval.strengths', [str(s) for s in analysis.get('strengths', [])]
        )
        span.set_attribute(
            'eval.improvement_areas',
            [str(a) for a in analysis.get('improvement_areas', [])],
        )
