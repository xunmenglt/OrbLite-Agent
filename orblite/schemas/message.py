

from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field

from orblite.schemas.base import Role
from orblite.schemas.tool import Function, ToolCall


class Message(BaseModel):
    """
    对话中的消息
    """

    role: Role= Field(...)  # type: ignore
    content: Optional[str] = Field(default=None)
    tool_calls: Optional[List[ToolCall]] = Field(default=None)
    tool_call_id: Optional[str] = Field(default=None)
    base64_image: Optional[str] = Field(default=None)
    
    def to_dict(self) -> dict:
        """Convert message to dictionary format"""
        message = {"role": self.role.value}
        if self.content is not None:
            message["content"] = self.content
        if self.tool_calls is not None:
            message["tool_calls"] = [tool_call.dict() for tool_call in self.tool_calls]
        if self.tool_call_id is not None:
            message["tool_call_id"] = self.tool_call_id
        if self.base64_image is not None:
            message["base64_image"] = self.base64_image
        return message
    
    @classmethod
    def user_message(
        cls, content: str, base64_image: Optional[str] = None
    ) -> "Message":
        """Create a user message"""
        return cls(role=Role.USER, content=content, base64_image=base64_image)
    
    @classmethod
    def system_message(cls, content: str,base64_image=None) -> "Message":
        """Create a system message"""
        return cls(role=Role.SYSTEM, content=content,base64_image=base64_image)
    
    @classmethod
    def assistant_message(
        cls, content: Optional[str] = None, base64_image: Optional[str] = None
    ) -> "Message":
        """Create an assistant message"""
        return cls(role=Role.ASSISTANT, content=content, base64_image=base64_image)
    
    @classmethod
    def tool_message(
        cls, content: str, tool_call_id: str, base64_image: Optional[str] = None
    ) -> "Message":
        """Create a tool message"""
        return cls(
            role=Role.TOOL,
            content=content,
            tool_call_id=tool_call_id,
            base64_image=base64_image,
        )
    
    @classmethod
    def from_tool_calls(
        cls,
        tool_calls: List[Any],
        content: Union[str, List[str]] = "",
        base64_image: Optional[str] = None,
        **kwargs,
    ):
        """Create ToolCallsMessage from raw tool calls.

        Args:
            tool_calls: Raw tool calls from LLM
            content: Optional message content
            base64_image: Optional base64 encoded image
        """
        formatted_calls = [
            ToolCall(
                id=call.id,
                type="function",
                function=Function(
                    name=call.function.model_dump()["name"],
                    arguments=call.function.model_dump()["arguments"],
                )
            ) for call in tool_calls
        ]
        return cls(
            role=Role.ASSISTANT,
            content=content,
            tool_calls=formatted_calls,
            base64_image=base64_image,
            **kwargs,
        )