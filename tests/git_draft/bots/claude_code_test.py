from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import git_draft.bots.claude_code as sut
from git_draft.bots.common import Goal, UserFeedback, Worktree


class TestNewBot:
    def test_creates_bot_instance(self) -> None:
        bot = sut.new_bot()
        assert isinstance(bot, sut._Bot)


class TestBot:
    def test_init_sets_options(self) -> None:
        bot = sut._Bot()
        expected_tools = ["Read", "Write", "mcp__feedback__ask_user"]
        assert bot._options.allowed_tools == expected_tools
        assert bot._options.permission_mode == "bypassPermissions"
        assert sut._PROMPT_SUFFIX in bot._options.append_system_prompt

    @patch("git_draft.bots.claude_code.sdk")
    @pytest.mark.asyncio
    async def test_act_basic_flow(self, mock_sdk) -> None:
        # Setup mocks
        mock_client = AsyncMock()
        mock_sdk.ClaudeSDKClient.return_value.__aenter__.return_value = (
            mock_client
        )

        # Create real message classes for pattern matching
        from dataclasses import dataclass
        from typing import Any

        @dataclass
        class UserMessage:
            content: str

        @dataclass
        class AssistantMessage:
            content: str
            extra: Any = None

        @dataclass
        class ResultMessage:
            num_turns: int = 3
            total_cost_usd: float = 0.05
            usage: dict = None

        @dataclass
        class SystemMessage:
            pass

        mock_sdk.UserMessage = UserMessage
        mock_sdk.AssistantMessage = AssistantMessage
        mock_sdk.ResultMessage = ResultMessage
        mock_sdk.SystemMessage = SystemMessage

        # Create message sequence with appropriate usage
        result_usage = {
            "input_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 50,
        }

        user_msg = UserMessage("user message")
        assistant_msg = AssistantMessage("assistant response", None)
        result_msg = ResultMessage(
            num_turns=3, total_cost_usd=0.05, usage=result_usage
        )
        system_msg = SystemMessage()

        async def mock_receive():
            for msg in [user_msg, assistant_msg, result_msg, system_msg]:
                yield msg

        mock_client.receive_response = mock_receive

        # Setup test objects
        goal = Goal(prompt="Test prompt")

        mock_worktree = MagicMock(spec=Worktree)
        mock_context = MagicMock()
        mock_context.__enter__.return_value = "/tmp/test"
        mock_context.__exit__.return_value = None
        mock_worktree.edit_files.return_value = mock_context

        mock_feedback = MagicMock(spec=UserFeedback)

        # Mock the ClaudeCodeOptions so dataclasses.replace works
        mock_replace_path = "git_draft.bots.claude_code.dataclasses.replace"
        with patch(mock_replace_path) as mock_replace:
            mock_replace.return_value = MagicMock(
                cwd="/tmp/test", mcp_servers={}
            )

            bot = sut._Bot()
            summary = await bot.act(goal, mock_worktree, mock_feedback)

        # Verify calls
        mock_client.query.assert_called_once_with("Test prompt")
        mock_feedback.notify.assert_any_call("user message")
        mock_feedback.notify.assert_any_call("assistant response")

        # Verify summary
        assert summary.turn_count == 3
        assert summary.cost == 0.05
        assert summary.token_count == 150


class TestTokenCount:
    def test_sums_all_tokens(self) -> None:
        usage = {
            "input_tokens": 100,
            "cache_creation_input_tokens": 20,
            "cache_read_input_tokens": 30,
            "output_tokens": 50,
        }
        result = sut._token_count(usage)
        assert result == 200

    def test_handles_zero_tokens(self) -> None:
        usage = {
            "input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 0,
        }
        result = sut._token_count(usage)
        assert result == 0


class TestNotify:
    def test_string_content(self) -> None:
        mock_feedback = MagicMock(spec=UserFeedback)
        sut._notify(mock_feedback, "test message")
        mock_feedback.notify.assert_called_once_with("test message")

    def test_list_content_with_text_blocks(self) -> None:
        mock_feedback = MagicMock(spec=UserFeedback)

        # Create classes that work with pattern matching
        from dataclasses import dataclass

        @dataclass
        class TextBlock:
            text: str

        text_block1 = TextBlock("First text")
        text_block2 = TextBlock("Second text")

        # Patch the SDK to use our classes
        with patch("git_draft.bots.claude_code.sdk") as mock_sdk:
            mock_sdk.TextBlock = TextBlock
            mock_sdk.ThinkingBlock = type("ThinkingBlock", (), {})
            mock_sdk.ToolUseBlock = type("ToolUseBlock", (), {})
            mock_sdk.ToolResultBlock = type("ToolResultBlock", (), {})

            content = [text_block1, text_block2]
            sut._notify(mock_feedback, content)

        mock_feedback.notify.assert_any_call("First text")
        mock_feedback.notify.assert_any_call("Second text")

    def test_list_content_with_thinking_blocks(self) -> None:
        mock_feedback = MagicMock(spec=UserFeedback)

        # Create class that works with pattern matching
        from dataclasses import dataclass

        @dataclass
        class ThinkingBlock:
            thinking: str
            signature: str

        thinking_block = ThinkingBlock("thinking content", "signature content")

        # Patch the SDK to use our classes
        with patch("git_draft.bots.claude_code.sdk") as mock_sdk:
            mock_sdk.TextBlock = type("TextBlock", (), {})
            mock_sdk.ThinkingBlock = ThinkingBlock
            mock_sdk.ToolUseBlock = type("ToolUseBlock", (), {})
            mock_sdk.ToolResultBlock = type("ToolResultBlock", (), {})

            content = [thinking_block]
            sut._notify(mock_feedback, content)

        mock_feedback.notify.assert_any_call("thinking content")
        mock_feedback.notify.assert_any_call("signature content")

    @patch("git_draft.bots.claude_code._logger")
    def test_list_content_with_tool_blocks(self, mock_logger) -> None:
        mock_feedback = MagicMock(spec=UserFeedback)

        # Create real classes for pattern matching
        class ToolUseBlock:
            pass

        class ToolResultBlock:
            pass

        tool_use_block = ToolUseBlock()
        tool_result_block = ToolResultBlock()

        # Patch the SDK to use our classes
        with patch("git_draft.bots.claude_code.sdk") as mock_sdk:
            mock_sdk.TextBlock = type("TextBlock", (), {})
            mock_sdk.ThinkingBlock = type("ThinkingBlock", (), {})
            mock_sdk.ToolUseBlock = ToolUseBlock
            mock_sdk.ToolResultBlock = ToolResultBlock

            content = [tool_use_block, tool_result_block]
            sut._notify(mock_feedback, content)

        # Should log but not notify
        assert mock_logger.debug.call_count == 2
        mock_feedback.notify.assert_not_called()

    def test_list_content_with_unknown_block_raises_error(self) -> None:
        mock_feedback = MagicMock(spec=UserFeedback)

        # Create real classes for pattern matching
        class TextBlock:
            pass

        class ThinkingBlock:
            pass

        class ToolUseBlock:
            pass

        class ToolResultBlock:
            pass

        class UnknownBlock:
            pass

        # Create a block that doesn't match any expected type
        unknown_block = UnknownBlock()

        # Patch the SDK to use our classes
        with patch("git_draft.bots.claude_code.sdk") as mock_sdk:
            mock_sdk.TextBlock = TextBlock
            mock_sdk.ThinkingBlock = ThinkingBlock
            mock_sdk.ToolUseBlock = ToolUseBlock
            mock_sdk.ToolResultBlock = ToolResultBlock

            content = [unknown_block]

            from git_draft.common import UnreachableError

            with pytest.raises(UnreachableError):
                sut._notify(mock_feedback, content)


class TestFeedbackMcpServer:
    @patch("git_draft.bots.claude_code.sdk")
    def test_creates_server_with_ask_user_tool(self, mock_sdk) -> None:
        mock_feedback = MagicMock(spec=UserFeedback)
        mock_feedback.ask.return_value = "user response"

        # Mock the decorator and server creation
        mock_tool_decorator = MagicMock()
        mock_sdk.tool.return_value = mock_tool_decorator
        mock_sdk.create_sdk_mcp_server.return_value = "mock_server"

        server = sut._feedback_mcp_server(mock_feedback)

        # Verify the decorator was called correctly
        mock_sdk.tool.assert_called_once_with(
            "ask_user", "Request feedback from the user", {"question": str}
        )

        # Verify server creation
        mock_sdk.create_sdk_mcp_server.assert_called_once()
        call_args = mock_sdk.create_sdk_mcp_server.call_args
        assert call_args[1]["name"] == "feedback"
        assert "tools" in call_args[1]

        assert server == "mock_server"

    @patch("git_draft.bots.claude_code.sdk")
    @pytest.mark.asyncio
    async def test_ask_user_tool_function(self, mock_sdk) -> None:
        mock_feedback = MagicMock(spec=UserFeedback)
        mock_feedback.ask.return_value = "user answer"

        # Capture the decorated function
        captured_function = None

        def mock_tool_decorator(func):
            nonlocal captured_function
            captured_function = func
            return func

        mock_sdk.tool.return_value = mock_tool_decorator
        mock_sdk.create_sdk_mcp_server.return_value = "mock_server"

        sut._feedback_mcp_server(mock_feedback)

        # Test the captured ask_user function
        args = {"question": "What is your name?"}
        result = await captured_function(args)

        mock_feedback.ask.assert_called_once_with("What is your name?")
        expected_result = {
            "content": [{"type": "text", "text": "user answer"}]
        }
        assert result == expected_result
