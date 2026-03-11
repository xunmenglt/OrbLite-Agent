from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from orblite.schemas.agent_req import AgentRequest
from orblite.schemas.context import AgentContext


class AgentHandlerService(BaseModel,ABC):
    """
    Agent 处理服务接口
    """

    @abstractmethod
    def handle(self, context: 'AgentContext', request: AgentRequest) -> str:
        """
        处理 Agent 请求
        :param context: Agent 上下文
        :param request: Agent 请求对象
        :return: 处理结果字符串
        """
        pass

    @abstractmethod
    def support(self, context: AgentContext, request: AgentRequest) -> bool:
        """
        判断是否满足进入当前 handler 的条件
        :param context: Agent 上下文
        :param request: Agent 请求对象
        :return: 是否支持处理
        """
        pass