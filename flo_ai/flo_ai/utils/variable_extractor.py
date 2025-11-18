"""
Variable extraction utilities for the Flo AI framework.

This module provides functions to extract variable placeholders from text,
inputs, and agent configurations for runtime variable validation.
"""

import re
from typing import List, Set, Dict, Any

from flo_ai.models.chat_message import BaseMessage, TextMessageContent, AssistantMessage


def extract_variables_from_text(text: str | AssistantMessage) -> Set[str]:
    """Extract variable placeholders from text using <variable_name> pattern.

    Args:
        text: Text containing variable placeholders like <variable_name>

    Returns:
        Set of variable names found in the text

    Examples:
        >>> extract_variables_from_text("Hello <name>, your <role> is important")
        {'name', 'role'}
        >>> extract_variables_from_text("No variables here")
        set()
    """
    if not text:
        return set()
    if isinstance(text, AssistantMessage):
        text_str = text.content
    elif isinstance(text, str):
        text_str = text

    # Use regex to find all <variable_name> patterns
    # \w+ matches word characters (letters, digits, underscore)
    variable_pattern = r'<(\w+)>'
    matches = re.findall(variable_pattern, text_str)
    return set(matches)


def extract_variables_from_inputs(inputs: List[BaseMessage]) -> Set[str]:
    """Extract variable placeholders from a list of input messages.

    Args:
        inputs: List of input strings or ImageMessages

    Returns:
        Set of variable names found across all string inputs

    Note:
        ImageMessageContent objects are skipped as they don't contain variable placeholders
    """
    all_variables = set()
    for input_item in inputs:
        if isinstance(input_item, BaseMessage):
            if isinstance(input_item.content, TextMessageContent):
                variables = extract_variables_from_text(input_item.content.text)
                all_variables.update(variables)
        if isinstance(input_item, str):
            variables = extract_variables_from_text(input_item)
            all_variables.update(variables)
        # Skip ImageMessageContent objects as they don't contain text variables

    return all_variables


def extract_agent_variables(agent) -> Set[str]:
    """Extract variable placeholders from an agent's system prompt.

    Args:
        agent: Agent instance with a system_prompt attribute

    Returns:
        Set of variable names found in the agent's system prompt

    Note:
        This function avoids importing Agent to prevent circular imports
    """
    if not hasattr(agent, 'system_prompt'):
        return set()

    return extract_variables_from_text(agent.system_prompt)


def validate_variables(
    required_variables: Set[str], provided_variables: Dict[str, Any], context: str = ''
) -> None:
    """Validate that all required variables are provided.

    Args:
        required_variables: Set of variable names that are required
        provided_variables: Dictionary of variable name to value mappings
        context: Optional context string for error messages (e.g., agent name)

    Raises:
        ValueError: If any required variables are missing
    """
    missing = required_variables - set(provided_variables.keys())
    if missing:
        available = list(provided_variables.keys()) if provided_variables else []
        context_str = f' for {context}' if context else ''
        raise ValueError(
            f'Missing required variables{context_str}: {sorted(missing)}. '
            f'Available variables: {available}'
        )


def resolve_variables(
    text: str | BaseMessage | AssistantMessage, variables: Dict[str, Any]
) -> str | BaseMessage | AssistantMessage:
    """Replace <variable_name> patterns with actual values

    Args:
        text: Text containing variable placeholders like <variable_name>
        variables: Dictionary of variable name to value mappings

    Returns:
        Text with variables resolved

    Raises:
        ValueError: If a variable placeholder is found but not provided in variables
    """
    if not text or not variables:
        return text

    def replace_var(match):
        var_name = match.group(1)
        if var_name in variables:
            return str(variables[var_name])
        else:
            available = list(variables.keys())
            raise ValueError(
                f"Variable '{var_name}' referenced in text but not provided. "
                f'Available variables: {available}'
            )

    return re.sub(r'<(\w+)>', replace_var, text)


def validate_multi_agent_variables(
    agents_variables: Dict[str, Set[str]], provided_variables: Dict[str, Any]
) -> None:
    """Validate variables for multiple agents and provide detailed error messages.

    Args:
        agents_variables: Dictionary mapping agent names to their required variables
        provided_variables: Dictionary of variable name to value mappings

    Raises:
        ValueError: If any agents are missing required variables, with detailed breakdown
    """
    missing_by_agent = {}
    provided_keys = set(provided_variables.keys())

    for agent_name, required_vars in agents_variables.items():
        missing = required_vars - provided_keys
        if missing:
            missing_by_agent[agent_name] = sorted(missing)

    if missing_by_agent:
        error_msg = 'Missing required variables for agents:\n'
        for agent_name, missing_vars in missing_by_agent.items():
            error_msg += f"  - Agent '{agent_name}': {missing_vars}\n"
        error_msg += f'Provided variables: {sorted(provided_keys)}'
        raise ValueError(error_msg)
