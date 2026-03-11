"""
基类Agent - 管理代理状态和执行的基础类别
"""
import json
import asyncio
from typing import Optional,List,Dict
from contextlib import asynccontextmanager
from pydantic import BaseModel,Field
from abc import ABC, abstractmethod
from orblite.schemas.base import AgentState, Role
from orblite.schemas.memory import Memory
from orblite.schemas.message import Message
from orblite.schemas.tool import ToolCall
from orblite.tool.tool_collection import ToolCollection
from orblite.printer.base import Printer
from orblite.llm import LLM
from orblite.schemas.context import AgentContext
from orblite.log_utils import logger


class BaseAgent(BaseModel,ABC):
    """用于管理智能体状态和执行的抽象基类。

    为状态转换、记忆管理和基于步骤的执行循环提供基础功能。子类必须实现 `step` 方法。
    """
    name:str = Field("",description="智能体名称")
    description:Optional[str] = Field(None,description="智能体描述")
    system_prompt:Optional[str] = Field(None,description="智能体系统提示词")
    next_step_prompt:Optional[str] = Field(None,description="决定下一动作的提示词")
    available_tools:ToolCollection = Field(default_factory=ToolCollection,description="可调用的工具集合")
    memory:Memory=Field(default_factory=Memory,description="当前智能体的记忆")
    llm:LLM=Field(default_factory=LLM,description="内置大模型")
    context:AgentContext=Field(default_factory=AgentContext,description="智能体上下文")

    # 执行控制
    state:AgentState=Field(default=AgentState.IDLE,description="当前Agent状态")
    max_steps:int=Field(default=10,description="最大执行步数")
    current_step: int = Field(default=0, description="当前已执行步数")
    duplicate_threshold: int = Field(default=2,description="重复次数")
    
    # 打印器
    printer:Optional[Printer]=Field(None,description="打印器")
    
    class Config:
        arbitrary_types_allowed = True
        extra = "allow"
    
    
    def update_memory(
        self,
        role: Role,  # type: ignore
        content: str,
        base64_image: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Add a message to the agent's memory.

        Args:
            role: The role of the message sender (user, system, assistant, tool).
            content: The message content.
            base64_image: Optional base64 encoded image.
            **kwargs: Additional arguments (e.g., tool_call_id for tool messages).

        Raises:
            ValueError: If the role is unsupported.
        """
        message_map = {
            "user": Message.user_message,
            "system": Message.system_message,
            "assistant": Message.assistant_message,
            "tool": lambda content, **kw: Message.tool_message(content, **kw),
        }

        if role.value not in message_map:
            raise ValueError(f"Unsupported message role: {role}")

        # Create message with appropriate parameters based on role
        kwargs = {"base64_image": base64_image, **(kwargs if role == "tool" else {})}
        self.memory.add_message(message_map[role](content, **kwargs))
    
    
    @abstractmethod
    async def step(self) -> str:
        """执行智能体工作流中的单个步骤。

        必须由子类实现以定义具体行为。
        """
        
    def is_stuck(self) -> bool:
        """通过检测重复内容来检查代理是否卡在循环中"""
        if len(self.memory.messages) < 2:
            return False

        last_message = self.memory.messages[-1]
        if not last_message.content:
            return False

        # Count identical content occurrences
        duplicate_count = sum(
            1
            for msg in reversed(self.memory.messages[:-1])
            if msg.role == "assistant" and msg.content == last_message.content
        )

        return duplicate_count >= self.duplicate_threshold

    def handle_stuck_state(self):
        """Handle stuck state by adding a prompt to change strategy"""
        stuck_prompt = "\
        观察到重复的回复。考虑新的策略，避免重复已经尝试过的无效路径。"
        self.next_step_prompt = f"{stuck_prompt}\n{self.next_step_prompt}"
        logger.warning(f"Agent detected stuck state. Added prompt: {stuck_prompt}")
    
    async def run(self,query:str)->None:
        """
        运行代理主循环
        """
        if self.state != AgentState.IDLE:
            raise RuntimeError(f"Cannot run agent from state: {self.state.value}")
        if query:
            self.update_memory(Role.USER,query,None)
        results: List[str] = []
        async with self.state_context(AgentState.RUNNING):
            while (self.current_step < self.max_steps and self.state != AgentState.FINISHED):
                self.current_step += 1
                logger.info(f"Executing step {self.current_step}/{self.max_steps}")
                step_result = await self.step()
                if self.is_stuck():
                    self.handle_stuck_state()
                results.append(f"Step {self.current_step}: {step_result}")
            if self.current_step >= self.max_steps:
                self.current_step = 0
                self.state = AgentState.IDLE
                results.append(f"Terminated: Reached max steps ({self.max_steps})")
            return results[-1] if results else "No steps executed"
        
    @asynccontextmanager
    async def state_context(self, new_state: AgentState):
        if not isinstance(new_state,AgentState):
            raise ValueError(f"Invalid state: {new_state}")
        previous_state = self.state
        self.state = new_state
        try:
            yield
        except Exception as e:
            self.state = AgentState.ERROR  # Transition to ERROR on failure
            raise e
        finally:
            self.state = previous_state  # Revert to previous state
    
    async def execute_tool(self,command:ToolCall)->str:
        if not command or not command.function or not command.function.name:
            return "Error: Invalid function call format"
        name=command.function.name
        try:
            args=json.loads(command.function.arguments)
            result=await self.available_tools.execute(name=name,tool_input=args)
            logger.info(f"{self.context.request_id} execute tool: {name} {args} result {result.output}")
            return result.output
        except Exception as e:
            logger.error(f"{self.context.request_id} execute tool {name} failed: {e}")
            raise e
        return f"Tool {name} Error."
    
    async def execute_tools(self,commands:List[ToolCall])->Dict[str,str]:
        result:Dict[str,str]={}
        for command in commands:
            tool_result = await self.execute_tool(command)
            result[command.id] = tool_result
        return result
    
    
    
    
    


