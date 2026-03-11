import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field

from orblite.log_utils import logger


class ToolResult(BaseModel):
    """工具执行结果"""

    output: Any = Field(default=None)
    error: Optional[str] = Field(default=None)
    base64_image: Optional[str] = Field(default=None)
    system: Optional[str] = Field(default=None)

    class Config:
        arbitrary_types_allowed = True

    def __bool__(self):
        return any(getattr(self, field) for field in self.__fields__)

    def __add__(self, other: "ToolResult"):
        def combine_fields(
            field: Optional[str], other_field: Optional[str], concatenate: bool = True
        ):
            if field and other_field:
                if concatenate:
                    return field + other_field
                raise ValueError("Cannot combine tool results")
            return field or other_field

        return ToolResult(
            output=combine_fields(self.output, other.output),
            error=combine_fields(self.error, other.error),
            base64_image=combine_fields(self.base64_image, other.base64_image, False),
            system=combine_fields(self.system, other.system),
        )

    def __str__(self):
        return f"Error: {self.error}" if self.error else self.output

    def replace(self, **kwargs):
        """Returns a new ToolResult with the given fields replaced."""
        # return self.copy(update=kwargs)
        return type(self)(**{**self.dict(), **kwargs})
    

class BaseTool(ABC, BaseModel):

    name: str=None
    description: str=None
    parameters: Optional[dict] = None
    # _schemas: Dict[str, List[ToolSchema]] = {}

    class Config:
        arbitrary_types_allowed = True
        underscore_attrs_are_private = False


    async def __call__(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        return await self.execute(**kwargs)

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""

    def to_param(self) -> Dict:
        """Convert tool to function call format.

        Returns:
            Dictionary with tool metadata in OpenAI function calling format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


    def success_response(self, data: Union[Dict[str, Any], str]) -> ToolResult:
        """Create a successful tool result.

        Args:
            data: Result data (dictionary or string)

        Returns:
            ToolResult with success=True and formatted output
        """
        if isinstance(data, str):
            text = data
        else:
            text = json.dumps(data, indent=2)
        logger.debug(f"Created success response for {self.__class__.__name__}")
        return ToolResult(output=text)

    def fail_response(self, msg: str) -> ToolResult:
        """Create a failed tool result.

        Args:
            msg: Error message describing the failure

        Returns:
            ToolResult with success=False and error message
        """
        logger.debug(f"Tool {self.__class__.__name__} returned failed result: {msg}")
        return ToolResult(error=msg)