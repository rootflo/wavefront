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
from opentelemetry import context as otel_context, trace

tracer = trace.get_tracer(__name__)

_EVAL_DIMENSIONS = [
    'goal_completion',
    'instruction_adherence',
    'conversation_quality',
    'response_efficiency',
    'language_handling',
    'turn_management',
    'factual_accuracy',
    'voice_delivery_quality',
    'compliance_safety',
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
        parent_context: Optional[otel_context.Context] = None,
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
                context=parent_context,
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
                # Add one span event per turn — no raw content to avoid PII in OTel
                for entry in transcript_log:
                    content = entry.get('content', '')
                    span.add_event(
                        'turn',
                        {
                            'role': entry.get('role', ''),
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
The voice agent may operate in multiple languages including English and regional languages (such as Hindi, Tamil, Malayalam, Kannada, Telugu, Bengali, Marathi, or code-mixed forms like Hinglish or Tanglish).

## Agent Objective (System Prompt)
{system_prompt}

## Transcript
{transcript_text}

## Evaluation Process
Before assigning scores, perform the following reasoning internally:
1. Identify the agent's primary objective from the system prompt.
2. Determine whether the conversation successfully progressed toward that objective.
3. Identify any major failures, including:
    hallucinated or fabricated information
    compliance or policy violations
    truncated responses or speech likely to break in TTS
    incorrect language usage or unnatural translation
    poor turn-taking or interruptions in the conversation
4. Check whether the agent stayed within its allowed scope and handled unknown questions safely.
5. Consider whether the responses would sound natural and complete when spoken aloud.
After completing this reasoning, assign scores for each evaluation dimension.
Do NOT output your reasoning. Only output the final JSON result.

## Evaluation Rubric
Score each dimension from 1 (very poor) to 10 (excellent).
Scoring guidance:
1-3 = major failure
4-5 = below expectations
6-7 = acceptable but flawed
8-9 = strong performance
10 = near perfect execution

## Dimensions
- goal_completion: Did the agent successfully achieve the objective defined in the system prompt?
- instruction_adherence: Did the agent follow all system prompt rules, restrictions, persona guidelines, and behavioural instructions?
- conversation_quality: Did the conversation flow naturally with a professional, clear, and human-like tone suitable for spoken interaction?
- response_efficiency: Were responses concise, relevant, and free from unnecessary repetition or verbosity?
- language_handling: Did the agent correctly understand and respond in the user's language with fluency and clarity, including appropriate grammar, vocabulary, and switching between languages such as English, Hindi, Tamil, Malayalam, Kannada, Telugu, Bengali, Marathi, or mixed forms like Hinglish?
- turn_management: Did the agent manage conversation turns effectively without interrupting the user, missing responses, causing awkward pauses, or breaking conversational flow?
- factual_accuracy: Did the agent avoid hallucinating or fabricating information and stay within its knowledge boundaries?
- voice_delivery_quality: Were responses suitable for spoken delivery without truncation, abrupt endings, incomplete words, or formatting that could break TTS playback?
- compliance_safety: Did the agent avoid sharing restricted information, violating policies, or creating regulatory risks?

## Output Format
Respond ONLY with a valid JSON object in this exact structure:
{{
  "overall_rating": <integer 1-10>,
  "detected_languages": ["<str>", "..."],
  "dimensions": {{
    "goal_completion":        {{"score": <integer 1-10>}},
    "instruction_adherence":  {{"score": <integer 1-10>}},
    "conversation_quality":   {{"score": <integer 1-10>}},
    "response_efficiency":    {{"score": <integer 1-10>}},
    "language_handling":      {{"score": <integer 1-10>}},
    "turn_management":        {{"score": <integer 1-10>}},
    "factual_accuracy":       {{"score": <integer 1-10>}},
    "voice_delivery_quality": {{"score": <integer 1-10>}},
    "compliance_safety":      {{"score": <integer 1-10>}}
  }},
  "strengths": ["<str>", "..."],
  "improvement_areas": ["<str>", "..."],
  "failure_tags": ["<only include tags that apply, from: hallucination | tts_truncation | policy_violation | missed_escalation | goal_not_met>"]
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

        timeout = aiohttp.ClientTimeout(total=40, connect=8, sock_read=32)
        async with aiohttp.ClientSession(timeout=timeout) as session:
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
        span.set_attribute(
            'eval.detected_languages',
            [str(lang) for lang in analysis.get('detected_languages', [])],
        )

        dimensions = analysis.get('dimensions', {})
        for dim in _EVAL_DIMENSIONS:
            dim_data = dimensions.get(dim, {})
            span.set_attribute(f'eval.{dim}', int(dim_data.get('score', 0)))

        span.set_attribute(
            'eval.strengths', [str(s) for s in analysis.get('strengths', [])]
        )
        span.set_attribute(
            'eval.improvement_areas',
            [str(a) for a in analysis.get('improvement_areas', [])],
        )
        span.set_attribute(
            'eval.failure_tags',
            [str(t) for t in analysis.get('failure_tags', [])],
        )
