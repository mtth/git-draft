"""Claude code bot implementations

Useful links:

* https://github.com/anthropics/claude-code
* https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-python
"""

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
    Make sure to use the feedback's MCP server ask_user tool if you need to
    request any information from the user.
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
        with tree.edit_files() as tree_path:
            options = dataclasses.replace(
                self._options,
                cwd=tree_path,
                mcp_servers={"feedback": _feedback_mcp_server(feedback)},
            )
            async with sdk.ClaudeSDKClient(options) as client:
                await client.query(goal.prompt)
                async for msg in client.receive_response():
                    match msg:
                        case sdk.UserMessage(content):
                            _notify(feedback, content)
                        case sdk.AssistantMessage(content, _):
                            _notify(feedback, content)
                        case sdk.SystemMessage(subtype, data):
                            _logger.debug(
                                "System message %s: %s", subtype, data
                            )
                        case sdk.ResultMessage() as message:
                            _logger.debug("Result message: %s", message)
                            if result := message.result:
                                _notify(feedback, result)
        return ActionSummary()


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
