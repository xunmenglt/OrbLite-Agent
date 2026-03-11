from typing import Optional,Any
from pydantic import BaseModel
from orblite.schemas.base import AgentType


class Printer(BaseModel):
    async def send(
        self,
        message_id: Optional[str] = None,
        message_type: str = "",
        message: Any = None,
        is_final: bool = False
    ) -> None:
        pass
    
    
    async def close(self) -> None:
        pass
    
    async def update_agent_type(self, agent_type: AgentType) -> None:
        pass
    
