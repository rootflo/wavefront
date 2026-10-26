"""System-message text of the browser (WebRTC) app flow (step context)."""

from typing import Optional

from call_processing.constants.language_config import LANGUAGE_DISPLAY_NAMES

# Added to the conversation so the agent opens the step it was just moved to
STEP_OPENER = '[The app moved to a new step. Follow the current step instructions and begin it now.]'


def build_step_opener(instruction: Optional[str]) -> str:
    """The user turn that opens a step, carrying the step's instruction when it has one.

    The instruction is also in the system prompt, but a long prompt plus a history of
    identical openers lets the LLM repeat its last answer; putting the instruction in the
    turn it answers keeps each step distinct.
    """
    if not instruction:
        return STEP_OPENER
    return f'{STEP_OPENER}\n{instruction}'


def is_step_opener(text: str) -> bool:
    return text.startswith(STEP_OPENER)


def step_heading(where: str) -> str:
    return f'CURRENT APP STEP: {where}'


def step_language_line(language: str) -> str:
    name = LANGUAGE_DISPLAY_NAMES.get(language, language)
    return f'Speak only in {name} (language code: {language}).'


def default_step_instruction(where: str) -> str:
    return (
        f'You are on step {where}. Only handle this step; do not move on by yourself.'
    )


def build_handoff_note(
    previous_name: str,
    new_name: str,
    *,
    new_step: bool = False,
    carry_history: bool = True,
) -> str:
    """System-injected user turn after a hot-swap.

    Does not ask the model to say its agent name — that fights prompts like
    "Don't mention agent name" and produces unnatural handoffs.
    ``new_name`` is kept in the signature for callers/tests; unused in the text.
    """
    del new_name  # reserved for logging/callers; never spoken in the note
    if not carry_history:
        # Clean context: there is no earlier conversation to refer to
        return (
            '[A conversation with the user is starting now and you have no earlier '
            'history with them. Briefly greet them and help. '
            'Do not say your agent name.]'
        )
    previous = f' from {previous_name}' if previous_name else ''
    if new_step:
        # The app moved on: the earlier topic is finished, not something to pick up again
        return (
            f'[You just took over this conversation{previous}. The conversation so far '
            f'is above for reference only: that step is finished. Do not continue, '
            f'repeat or finish what was being said before. Start the current step '
            f'now. Do not say your agent name.]'
        )
    return (
        f'[You just took over this conversation{previous}. The conversation so far '
        f'is above. Continue helping the user where the conversation left off. '
        f'Do not repeat earlier answers. Do not say your agent name.]'
    )
