from typing import Any, Dict, List
from pydantic import BaseModel,Field
from orblite.tool.base import ToolResult
from orblite.log_utils import logger
from orblite.tool.base import BaseTool

class ToolCollection(BaseModel):
    tool_map:Dict[str,BaseTool]=Field(default_factory=dict)
    
    def add_tool(self,tool:BaseTool) -> "ToolCollection":
        self.tool_map[tool.name]=tool
        return self
    
    def get_tool(self,name:str)->BaseTool:
        return self.tool_map.get(name)
    
    async def execute(self,name:str,tool_input:Dict[str,Any]) -> ToolResult:
        if name in self.tool_map:
            tool=self.get_tool(name)
            return await tool.execute(**tool_input)
        else:
            logger.error("Error: Unknown tool {name}")
        return None
    
    def to_dict(self)->Dict:
        res=[]
        for tool in self.tool_map.values():
            tool_dict={
                "type":"function",
                "function":{
                    "name":tool.name,
                    "description":tool.description,
                    "parameters":tool.parameters,
                }
            }
            res.append(tool_dict)
        return res
    
    
    
    