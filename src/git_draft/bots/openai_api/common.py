"""Shared OpenAI abstractions"""

from collections.abc import Mapping, Sequence
import json
import logging
from pathlib import PurePosixPath
from typing import Any

import openai

from ...common import UnreachableError, config_string, reindent
from ..common import UserFeedback, Worktree


_logger = logging.getLogger(__name__)


def new_client(api_key: str | None, base_url: str | None) -> openai.OpenAI:
    return openai.OpenAI(
        api_key=config_string(api_key) if api_key else None,
        base_url=base_url,
    )


class ToolsFactory:
    """Tool definition helper"""

    def __init__(self, strict: bool) -> None:
        self._strict = strict

    def _param(
        self,
        name: str,
        description: str,
        inputs: Mapping[str, Any] | None = None,
        _required_inputs: Sequence[str] | None = None,
    ) -> openai.types.beta.FunctionToolParam:
        param: openai.types.beta.FunctionToolParam = {
            "type": "function",
            "function": {
                "name": name,
                "description": reindent(description),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": inputs or {},
                    "required": list(inputs.keys()) if inputs else [],
                },
            },
        }
        if self._strict:
            param["function"]["strict"] = True
        return param

    def params(self) -> Sequence[openai.types.chat.ChatCompletionToolParam]:
        return [
            self._param(
                name="ask_user",
                description="""
                    Request more information from the user

                    Call this function if and only if you are unable to achieve
                    your task with the information you already have.
                """,
                inputs={
                    "question": {
                        "type": "string",
                        "description": "Question to be answered by the user",
                    },
                },
            ),
            self._param(
                name="list_files",
                description="List all available files",
            ),
            self._param(
                name="read_file",
                description="Get a file's contents",
                inputs={
                    "path": {
                        "type": "string",
                        "description": "Path of the file to be read",
                    },
                },
            ),
            self._param(
                name="write_file",
                description="""
                    Set a file's contents

                    The file will be created if it does not already exist.
                """,
                inputs={
                    "path": {
                        "type": "string",
                        "description": "Path of the file to be updated",
                    },
                    "contents": {
                        "type": "string",
                        "description": "New contents of the file",
                    },
                },
            ),
            self._param(
                name="delete_file",
                description="Delete a file",
                inputs={
                    "path": {
                        "type": "string",
                        "description": "Path of the file to be deleted",
                    },
                },
            ),
            self._param(
                name="rename_file",
                description="Rename a file",
                inputs={
                    "src_path": {
                        "type": "string",
                        "description": "Old file path",
                    },
                    "dst_path": {
                        "type": "string",
                        "description": "New file path",
                    },
                },
            ),
        ]


class ToolHandler[V]:
    """Tool handling base class"""

    def __init__(self, tree: Worktree, feedback: UserFeedback) -> None:
        self._tree = tree
        self._feedback = feedback

    def _on_ask_user(self, response: str) -> V:
        raise NotImplementedError()

    def _on_read_file(self, path: PurePosixPath, contents: str | None) -> V:
        raise NotImplementedError()

    def _on_write_file(self, path: PurePosixPath) -> V:
        raise NotImplementedError()

    def _on_delete_file(self, path: PurePosixPath) -> V:
        raise NotImplementedError()

    def _on_rename_file(
        self, src_path: PurePosixPath, dst_path: PurePosixPath
    ) -> V:
        raise NotImplementedError()

    def _on_list_files(self, paths: Sequence[PurePosixPath]) -> V:
        raise NotImplementedError()

    def handle_function(self, function: Any) -> V:
        inputs = json.loads(function.arguments)
        _logger.info("Requested function: %s", function)
        match function.name:
            case "ask_user":
                question = inputs["question"]
                response = self._feedback.ask(question)
                return self._on_ask_user(response)
            case "read_file":
                path = PurePosixPath(inputs["path"])
                return self._on_read_file(path, self._tree.read_file(path))
            case "write_file":
                path = PurePosixPath(inputs["path"])
                contents = inputs["contents"]
                self._tree.write_file(path, contents)
                return self._on_write_file(path)
            case "delete_file":
                path = PurePosixPath(inputs["path"])
                self._tree.delete_file(path)
                return self._on_delete_file(path)
            case "rename_file":
                src_path = PurePosixPath(inputs["src_path"])
                dst_path = PurePosixPath(inputs["dst_path"])
                self._tree.rename_file(src_path, dst_path)
                return self._on_rename_file(src_path, dst_path)
            case "list_files":
                paths = self._tree.list_files()
                return self._on_list_files(paths)
            case _ as name:
                raise UnreachableError(f"Unexpected function: {name}")
