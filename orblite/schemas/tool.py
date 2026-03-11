from pydantic import BaseModel
class Function(BaseModel):
    name: str
    arguments: str


class ToolCall(BaseModel):
    """
    a tool/function call in a message
    """
    id: str
    type: str = "function"
    function: Function