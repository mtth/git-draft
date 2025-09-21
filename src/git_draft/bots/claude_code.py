"""Claude code bot implementations

Useful links:

* https://github.com/anthropics/claude-code
* https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-python
"""

from collections.abc import Mapping
import dataclasses
import logging
from typing import Any

import claude_code_sdk as sdk

from ..common import UnreachableError, reindent
from .common import ActionSummary, Bot, Goal, UserFeedback, Worktree


_logger = logging.getLogger(__name__)


def new_bot() -> Bot:
    return _Bot()


_PROMPT_SUFFIX = reindent("""
    ALWAYS use the feedback's MCP server ask_user tool if you need to request
    any information from the user. NEVER repeat yourself by also asking your
    question to the user in other ways.
""")


class _Bot(Bot):
    def __init__(self) -> None:
        self._options = sdk.ClaudeCodeOptions(
            allowed_tools=["Read", "Write", "mcp__feedback__ask_user"],
            permission_mode="bypassPermissions",  # TODO: Tighten
            append_system_prompt=_PROMPT_SUFFIX,
        )

    async def act(
        self, goal: Goal, tree: Worktree, feedback: UserFeedback
    ) -> ActionSummary:
        summary = ActionSummary()
        with tree.edit_files() as tree_path:
            options = dataclasses.replace(
                self._options,
                cwd=tree_path,
                mcp_servers={"feedback": _feedback_mcp_server(feedback)},
            )
            async with sdk.ClaudeSDKClient(options) as client:
                await client.query(goal.prompt)
                async for msg in client.receive_response():
                    _logger.debug("SDK message: %s", msg)
                    match msg:
                        case sdk.UserMessage(content):
                            _notify(feedback, content)
                        case sdk.AssistantMessage(content, _):
                            _notify(feedback, content)
                        case sdk.ResultMessage() as message:
                            # This message's result appears to be identical to
                            # the last assistant message's content, so we do
                            # not need to show it.
                            summary.turn_count = message.num_turns
                            if usage := message.usage:
                                summary.token_count = _token_count(usage)
                            summary.usage_details = message.usage
                            summary.cost = message.total_cost_usd
                        case sdk.SystemMessage():
                            pass  # TODO: Notify on tool usage?
        return summary


def _token_count(usage: Mapping[str, Any]) -> int:
    return (
        usage["input_tokens"]
        + usage["cache_creation_input_tokens"]
        + usage["cache_read_input_tokens"]
        + usage["output_tokens"]
    )


def _notify(
    feedback: UserFeedback, content: str | list[sdk.ContentBlock]
) -> None:
    if isinstance(content, str):
        feedback.notify(content)
        return

    for block in content:
        match block:
            case sdk.TextBlock(text):
                feedback.notify(text)
            case sdk.ThinkingBlock(thinking, signature):
                feedback.notify(thinking)
                feedback.notify(signature)
            case sdk.ToolUseBlock() | sdk.ToolResultBlock() as block:
                _logger.debug("Using tool: %s", block)
            case _:
                raise UnreachableError()


def _feedback_mcp_server(feedback: UserFeedback) -> sdk.McpServerConfig:
    @sdk.tool("ask_user", "Request feedback from the user", {"question": str})
    async def ask_user(args: Any) -> Any:
        question = args["question"]
        return {"content": [{"type": "text", "text": feedback.ask(question)}]}

    return sdk.create_sdk_mcp_server(name="feedback", tools=[ask_user])
