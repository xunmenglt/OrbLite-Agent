
from typing import List
from pydantic import BaseModel, Field

from orblite.schemas.base import Role
from orblite.schemas.message import Message


class Memory(BaseModel):
    """
    消息记忆
    """
    messages:List[Message]=Field(default_factory=list)
    max_messages:int=Field(default=10000)
    
    def add_message(self,message:Message)-> None:
        self.messages.append(message)
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages :]
            
    def add_messages(self, messages: List[Message]) -> None:
        self.messages.extend(messages)
        if len(self.messages) > self.max_messages:
            self.messages=self.messages[-self.max_messages:]

    def clear(self) -> None:
        """Clear all messages"""
        self.messages.clear()
        
    def get_recent_messages(self, n: int) -> List[Message]:
        """Get n most recent messages"""
        return self.messages[-n:]
    
    def to_dict_list(self) -> List[dict]:
        """Convert messages to list of dicts"""
        return [msg.to_dict() for msg in self.messages]
    
    def get_last_message(self) -> Message:
        if self.messages:
            return self.messages[-1]
        else:
            return None
        
    def clear_tool_context(self) -> None:
        """
        清除工具相关的上下文消息
        """
        filtered_messages = []
        for msg in self.messages:
            if msg.role == Role.TOOL:
                continue
            if msg.role==Role.ASSISTANT and msg.tool_calls:
                continue
            if msg.content and msg.content.startswith("根据当前状态和可用工具，确定下一步行动"):
                continue
            filtered_messages.append(msg)
        self.messages=filtered_messages
    
    def get_format_message(self) -> str:
        res=""
        for msg in self.messages:
            res+=f"role:{msg.role.value} content:{msg.content}\n"
        return res
    
    def size(self) -> int:
        return len(self.messages)
    
    def is_empty(self) -> bool:
        return not (self.messages and len(self.messages>0))
    
    def get(self,index) -> Message:
        if index>=self.size():
            return None
        return self.messages[index]