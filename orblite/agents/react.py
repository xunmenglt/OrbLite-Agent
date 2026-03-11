from abc import ABC, abstractmethod
from orblite.agents.base import BaseAgent

class ReActAgent(BaseAgent,ABC):
    
    @abstractmethod
    async def think(self)->bool:
        """执行思考"""
    
    @abstractmethod
    async def act(self)->str:
        """执行行动"""
    
    
    async def step(self):
        should_act=await self.think()
        if not should_act:
            return "Thinking complete - no action needed"
        return await self.act()


    