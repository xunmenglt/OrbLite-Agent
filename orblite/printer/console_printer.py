from orblite.printer.base import Printer
from typing import Optional,Any
from orblite.schemas.base import AgentType

# 具体实现类
class ConsolePrinter(Printer):
    agent_type: Optional[AgentType] = None
    
    async def send(
        self,
        message_id: Optional[str] = None,
        message_type: str = "",
        message: Any = None,
        is_final: bool = False
    ) -> None:
        print(f"<PRINT>[{message_type}]: {message}")
        if is_final:
            print("--- 结束 ---")
    
    async def close(self) -> None:
        print("连接已关闭")
    
    async def update_agent_type(self, agent_type: AgentType) -> None:
        self.agent_type = agent_type
        print(f"智能体类型更新为：{agent_type.value}")