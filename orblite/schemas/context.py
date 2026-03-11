from pydantic import BaseModel, Field
from typing import Optional,List,Any
from orblite.printer.base import Printer
from orblite.tool.tool_collection import ToolCollection
from orblite.utils.file_util import File



class AgentContext(BaseModel):
    request_id: Optional[str]=None
    session_id: Optional[str]=None
    query: Optional[str]=None
    task: Optional[str]=None
    printer: Optional[Printer] = None
    tool_collection: Optional[ToolCollection] = None
    date_info: Optional[str] = None
    product_files: Optional[List[File]] = Field(default_factory=list)
    is_stream: bool = False
    stream_message_type: Optional[str] = None
    sop_prompt: Optional[str] = Field("")
    base_prompt: Optional[str] = Field("")
    agent_type: Optional[str] = None
    task_product_files: Optional[List[File]] = None
    template_type: Optional[str] = None