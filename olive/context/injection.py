# cli/olive/context/injection.py
from functools import wraps
from typing import Callable, List, Union, Literal, Dict
from olive.logger import get_logger

logger = get_logger(__name__)

PromptRole = Literal["system", "user"]
_CONTEXT_INJECTORS: Dict[PromptRole, List[Callable[[], List[dict]]]] = {
    "system": [],
    "user": [],
}


def olive_context_injector(role: PromptRole = "system"):
    """
    Register a function that returns prompt messages to inject during context hydration.

    Usage:
        @olive_context_injector()              # defaults to system
        @olive_context_injector("user")        # for user messages
    """

    def decorator(func: Callable[[], List[dict]]) -> Callable[[], List[dict]]:
        @wraps(func)
        def wrapper():
            return func()

        _CONTEXT_INJECTORS[role].append(wrapper)
        return wrapper

    return decorator


def get_context_injections(role: PromptRole = "system") -> List[dict]:
    """Run all registered injectors for a given role and return merged messages."""
    messages = []
    for fn in _CONTEXT_INJECTORS[role]:
        try:
            messages.extend(fn())
        except Exception as e:
            logger.warning(f"Failed {role} prompt injector {fn.__name__}: {e}")
    return messages


def append_context_injection(message: Union[str, dict], role: PromptRole = "system"):
    """
    Register a one-off prompt message for injection.

    Accepts:
        - str: treated as a message with specified role
        - dict: must include the correct role and a 'content' field

    Raises:
        ValueError or TypeError for malformed inputs
    """
    if isinstance(message, str):
        wrapped = {"role": role, "content": message}
    elif isinstance(message, dict):
        if message.get("role") != role or "content" not in message:
            logger.error(f"Invalid {role} message injection: {message}")
            raise ValueError(
                f"{role.title()} prompt injection must have role='{role}' and a 'content' field."
            )
        wrapped = message
    else:
        raise TypeError(
            "Prompt injection must be a string or a dict with 'role' and 'content'."
        )

    def inline_injector():
        return [wrapped]

    _CONTEXT_INJECTORS[role].append(inline_injector)
    logger.debug(f"Registered {role} prompt: {wrapped['content'][:60]}...")
