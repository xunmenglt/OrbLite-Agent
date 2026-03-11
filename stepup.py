import asyncio
from datetime import datetime
from typing import List
from orblite.config import config
from orblite.printer.console_printer import ConsolePrinter
from orblite.prompts.executor import sop_prompt
from orblite.schemas.agent_req import AgentRequest
from orblite.schemas.base import AgentType
from orblite.schemas.context import AgentContext
from orblite.service.plan_solve_handler import PlanSolveHandler
from orblite.tool.base import BaseTool
from orblite.tool.common.file_tool import FileTool
from orblite.tool.mcp.mcp_tool import MCPTool
from orblite.tool.tool_collection import ToolCollection
from orblite.utils.secrets import generate_random_id

async def _init_mcp_tools()->List[BaseTool]:
    total_tools=[]
    for mcp_item in config.mcp_config.servers.values():
        client=MCPTool(
            name=mcp_item.name,
            description=mcp_item.description,
            server_url=mcp_item.url,
            req_headers=mcp_item.headers
        )
        tools=await client.list_tool()
        total_tools.extend(tools)
    return total_tools
async def _init_tool_collection()->ToolCollection:
    tool_collection=ToolCollection()
    tools=await _init_mcp_tools()
    for tool in tools:
        tool_collection.add_tool(tool)

    return tool_collection

async def run():
    tool_collection=await _init_tool_collection()
    printer = ConsolePrinter()
    request_id=generate_random_id()
    request=AgentRequest(
        request_id=request_id,
        agent_type=AgentType.PLAN_SOLVE,
        query="针对苏大本部周边1.5公里生活圈，调研‘老旧社区活化与年轻人深夜消费需求’的匹配度报告。以html文件精美呈现",
        sop_prompt=""
    )
    agent_context=AgentContext(
        request_id=request_id,
        session_id=request_id,
        printer=printer,
        query=request.query,
        task="",
        date_info=datetime.now().isoformat(),
        sop_prompt="",
        agent_type=request.agent_type,
        is_stream=request.is_stream
    )
    file_tool=FileTool(
        agent_context=agent_context
    )
    tool_collection.add_tool(file_tool)
    agent_context.tool_collection=tool_collection
    handler=PlanSolveHandler()
    await handler.handle(agent_context,request)

    
    
    

if __name__=="__main__":
    asyncio.run(run())
    