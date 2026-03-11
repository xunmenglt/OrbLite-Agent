from enum import Enum
from typing import Literal

class Role(str, Enum):
    """Message role options"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

ROLE_VALUES = tuple(role.value for role in Role)
ROLE_TYPE = Literal[ROLE_VALUES]  # type: ignore

class ToolChoice(str, Enum):
    """Tool choice options"""

    NONE = "none"
    AUTO = "auto"
    REQUIRED = "required"
    
TOOL_CHOICE_VALUES = tuple(choice.value for choice in ToolChoice)
TOOL_CHOICE_TYPE = Literal[TOOL_CHOICE_VALUES]  # type: ignore


class AgentState(str, Enum):
    """智能体执行状态"""

    IDLE = "IDLE" # 空闲状态
    RUNNING = "RUNNING" # 运行状态
    FINISHED = "FINISHED" # 结束状态
    ERROR = "ERROR" # 错误状态
    

class AgentType(str,Enum):
    COMPREHENSIVE="COMPREHENSIVE"
    WORKFLOW="WORKFLOW"
    PLAN_SOLVE="PLAN_SOLVE"
    ROUTER="ROUTER"
    REACT="REACT"
