from typing import List, Optional
from pydantic import BaseModel, Field

from orblite.schemas.base import AgentType
from orblite.schemas.message import Message


class AgentRequest(BaseModel):
    request_id: str = Field(..., alias="requestId", description="请求的唯一标识符")
    query: str = Field(..., description="用户的自然语言问题或任务描述")
    agent_type: AgentType = Field(..., alias="agentType", description="智能体类型")
    
    base_prompt: Optional[str] = Field(None, alias="basePrompt", description="基础系统提示词")
    
    is_stream: bool = Field(False, alias="isStream", description="是否流式输出")
    messages: List[Message] = Field(default_factory=list, description="消息列表，支持多轮对话")
    
    # 交付物产出格式：html(网页模式）， docs(文档模式）， table(表格模式）
    output_style: Optional[str] = Field("html", alias="outputStyle", description="输出格式类型")

    class Config:
        # 允许使用驼峰命名进行初始化，同时也支持 Python 风格的下划线命名
        populate_by_name = True