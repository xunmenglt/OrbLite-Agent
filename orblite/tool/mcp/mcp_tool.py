from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import ListToolsResult, TextContent
from pydantic import BaseModel, Field

from orblite.log_utils import logger
from orblite.tool.base import BaseTool,ToolResult



class MCPTool(BaseTool):
    """可以从客户端在MCP服务器上调用的工具代理"""
    server_url:str=Field(...,description="mcp服务地址")
    session:ClientSession=Field(None,description="当前mcp会话")
    exit_stack:AsyncExitStack=Field(None)
    req_headers:Dict[str,Any]=Field(default_factory=dict,description="连接头")
    
    async def connect(self) -> None:
        """Connect to an MCP server using SSE transport."""
        if not self.server_url:
            raise ValueError("Server URL is required.")

        # Always ensure clean disconnection before new connection
        if self.session:
            await self.disconnect()

        self.exit_stack = AsyncExitStack()

        streams_context = sse_client(url=self.server_url,headers=self.req_headers)
        streams = await self.exit_stack.enter_async_context(streams_context)
        session = await self.exit_stack.enter_async_context(ClientSession(*streams))
        self.session = session
    
    async def disconnect(self) -> None:
        """Disconnect from a specific MCP server or all servers if no server_id provided."""
        if self.session:
            try:
                # Close the exit stack which will handle session cleanup
                if self.exit_stack:
                    try:
                        await self.exit_stack.aclose()
                    except RuntimeError as e:
                        if "cancel scope" in str(e).lower():
                            logger.warning(
                                f"Cancel scope error during disconnect from {self.server_url}, continuing with cleanup: {e}"
                            )
                        else:
                            raise

                # Clean up references
                self.session=None
                self.exit_stack=None
                logger.info(f"Disconnected from MCP server {self.server_url}")
            except Exception as e:
                logger.error(f"Error disconnecting from server {self.server_url}: {e}")
    
    
        
    async def list_tool(self)->List[BaseTool]:
        """Initialize session and populate tool map."""
        tools=[]
        try:
            if not self.session:
                await self.connect()
            await self.session.initialize()
            response = await self.session.list_tools()
            for tool in response.tools:
                tool_name = tool.name
                mcp_tool = MCPTool(
                    name=tool_name,
                    description=tool.description,
                    parameters=tool.inputSchema,
                    server_url=self.server_url,
                    req_headers=self.req_headers
                )
                tools.append(mcp_tool)
        finally:
            await self.disconnect()
        return tools
    
    
    async def execute(self,**kwargs) -> ToolResult:
        """通过远程呼叫 MCP 服务器来执行该工具。"""
        try:
            if not self.session:
                await self.connect()
            await self.session.initialize()
            logger.info(f"Executing tool: {self.name}")
            result = await self.session.call_tool(self.name, arguments=kwargs)
            content_str = ", ".join(
                item.text for item in result.content if isinstance(item, TextContent)
            )
            return ToolResult(output=content_str or "No output returned.")
        except Exception as e:
            return ToolResult(error=f"Error executing tool: {str(e)}")
        finally:
            await self.disconnect()
        