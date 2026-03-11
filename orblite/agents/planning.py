import json
from typing import List
from jinja2 import Template,DebugUndefined

from pydantic import Field, model_validator
from orblite.agents.react import ReActAgent
from orblite.exceptions import TokenLimitExceeded
from orblite.llm import LLM
from orblite.log_utils import logger
from orblite.schemas.base import AgentState,  Role, ToolChoice

from orblite.prompts.planner import system_prompt,next_step_prompt,pre_prompt
from orblite.config import config as orblite_config
from orblite.schemas.message import Message
from orblite.schemas.tool import Function, ToolCall
from orblite.utils import file_util
from orblite.tool.common.planning import PlanningTool

class PlanningAgent(ReActAgent):
    tool_calls:List[ToolCall]=Field(default_factory=list)
    max_observe:int=10000
    planning_tool:PlanningTool=Field(default_factory=PlanningTool)
    is_close_update:bool=Field(False)
    system_prompt_snapshot:str=Field(default="")
    next_step_prompt_snapshot:str=Field(default="")
    plan_id:str=Field(default="")
    
    @model_validator(mode="after")
    def initialize_helper(self)->"PlanningAgent":
        self.name="planning"
        self.description="创建和管理解决任务计划的智能体"
        tool_prompt=""
        for tool in self.context.tool_collection.tool_map.values():
            tool_prompt+=f"工具名：{tool.name} 工具描述：{tool.description}\n"

        self.system_prompt=Template(system_prompt,undefined=DebugUndefined).render(
            tools=tool_prompt,
            query=self.context.query,
            date=self.context.date_info,
            sopPrompt=self.context.sop_prompt
        )
        self.next_step_prompt=Template(next_step_prompt,undefined=DebugUndefined).render(
            tools=tool_prompt,
            query=self.context.query,
            date=self.context.date_info,
            sopPrompt=self.context.sop_prompt
        )
        self.system_prompt_snapshot=self.system_prompt
        self.next_step_prompt_snapshot=self.next_step_prompt
        
        self.printer=self.context.printer
        
        self.max_steps=orblite_config.orb_lite_planner.max_steps
        self.llm=LLM(orblite_config.orb_lite_planner.model_name)
        self.is_close_update=orblite_config.orb_lite_planner.close_update
        
        self.available_tools.add_tool(self.planning_tool)
        return self
    


    async def think(self) -> bool:
        # 获取文件内容
        file_str=file_util.format_file_info(self.context.product_files,False)
        self.system_prompt=Template(self.system_prompt_snapshot,undefined=DebugUndefined).render(
            files=file_str,
        )
        self.next_step_prompt=Template(self.next_step_prompt_snapshot,undefined=DebugUndefined).render(
            files=file_str,
        )
        logger.info(f"{self.context.request_id} planer fileStr {file_str}")
        
        if self.is_close_update:
            if self.planning_tool.plan:
                self.planning_tool.step_plan()
                return True
        try:
            if self.memory and not self.memory.get_last_message().role==Role.USER:
                user_msg=Message.user_message(self.next_step_prompt)
                self.memory.add_message(user_msg)
            # 将系统消息类型设置为‘计划思考’
            self.context.stream_message_type="plan_thought"
            ask_result=await self.llm.ask_tool(
                messages=self.memory.messages,
                system_msgs=(
                    [Message.system_message(self.system_prompt)]
                    if self.system_prompt
                    else None
                ),
                tools=self.available_tools,
                tool_choice=ToolChoice.AUTO,
                temperature=None,
                stream=self.context.is_stream,
                timeout=300
            )
        except ValueError:
            raise
        except Exception as e:
            if hasattr(e, "__cause__") and isinstance(e.__cause__, TokenLimitExceeded):
                token_limit_error = e.__cause__
                logger.error(
                    f"🚨 Token limit error (from RetryError): {token_limit_error}"
                )
                self.memory.add_message(
                    Message.assistant_message(
                        f"Maximum token limit reached, cannot continue execution: {str(token_limit_error)}"
                    )
                )
                self.state = AgentState.FINISHED
                return False
            raise
        tool_calls = (
            ask_result.tool_calls if ask_result and ask_result.tool_calls else []
        )
        self.tool_calls=[
            ToolCall(id=item.id,type=item.type,function=Function(name=item.function.name,arguments=item.function.arguments))
            for item in tool_calls
        ]
        if ask_result.content:
            await self.printer.send(message_type="plan_thought",message=ask_result.content)
        logger.info(f"{self.context.request_id} {self.name}'s thoughts: {ask_result.content}")
        logger.info(f"{self.context.request_id} {self.name} selected {len(self.tool_calls)} tools to use")
        if self.tool_calls:
            assistant_msg=Message.from_tool_calls(content=ask_result.content,tool_calls=tool_calls)
        else:
            assistant_msg=Message.assistant_message(content=ask_result.content)
        self.memory.add_message(assistant_msg)
        return True
    
    
    async def act(self) -> str:
        if self.is_close_update:
            if self.planning_tool and self.planning_tool.plan:
                return await self.get_next_task()
        results = []
        for tool_call in self.tool_calls:
            result=await self.execute_tool(tool_call)
            if self.max_observe:
                result_str=json.dumps(result,ensure_ascii=False)
                result_str = result_str[:min(len(result_str),self.max_observe)]
                results.append(result_str)
                # 添加工具到记忆
                tool_msg=Message.tool_message(
                    content=result,
                    tool_call_id=tool_call.id
                )
                self.memory.add_message(tool_msg)
        if self.planning_tool.plan:
            if self.is_close_update:
                self.planning_tool.step_plan()
            return await self.get_next_task()
        return "\n\n".join(results)
    
            
    
    async def get_next_task(self)->str:
        all_complete=True
        for status in self.planning_tool.plan.step_status:
            if "completed"!=status:
                all_complete=False
                break
        if all_complete:
            self.state=AgentState.FINISHED
            await self.printer.send(
                message_type="plan_updated",
                message={
                    "plan": self.planning_tool.plan,
                    "planDetail": self.planning_tool.get_format_plan(),
                },
            )
            return "finish"
        if self.planning_tool.plan.get_current_step():
            self.state=AgentState.FINISHED
            current_steps=self.planning_tool.plan.get_current_step().split("<sep>")
            await self.printer.send(
                message_type="plan_updated",
                message={
                    "plan": self.planning_tool.plan,
                    "planDetail": self.planning_tool.get_format_plan(),
                },
            )
            for step in current_steps:
                await self.printer.send(message_type="task",message=step)
            return self.planning_tool.plan.get_current_step()
        return ""

    async def run(self,query):
        if not self.planning_tool.plan:
            query=pre_prompt+query
        return await super().run(query)
        
        
    
    
    