import json
from typing import Optional,List
from jinja2 import Template,DebugUndefined

from pydantic import Field, model_validator
from orblite.agents.planning import orblite_config
from orblite.agents.react import ReActAgent
from orblite.exceptions import TokenLimitExceeded
from orblite.llm import LLM
from orblite.log_utils import logger
from orblite.schemas.base import AgentState,Role, ToolChoice
from orblite.prompts.executor import system_prompt,next_step_prompt,sop_prompt
from orblite.prompts.common import digital_employee_prompt,pre_prompt
from orblite.schemas.message import Message
from orblite.schemas.tool import Function, ToolCall
from orblite.utils import file_util


class ExecutorAgent(ReActAgent):
    tool_calls:List[ToolCall]=Field(default_factory=list,description="将要调用的工具列表")
    max_observe:int=Field(10000,description="最大观察内容长度")
    system_prompt_snapshot:Optional[str]=Field(None,description="系统prompt")
    next_step_prompt_snapshot:Optional[str]=Field(None,description="下一步Prompt")
    digital_employee_prompt:Optional[str]=Field(digital_employee_prompt,description="数字员工生成prompt")
    task_id:int=Field(9,description="任务ID")
    clear_tool_message:bool=Field(True,description="在执行完成之后是否清空工具执行结果")
    
    
    @model_validator(mode="after")
    def post_init(self)->"ExecutorAgent":
        self.name="executor"
        self.description="一个能调用Tool的智能体"
        tool_prompt=""
        for tool in self.context.tool_collection.tool_map.values():
            tool_prompt+=f"工具名：{tool.name} 工具描述：{tool.description}\n"
        self.system_prompt=Template(system_prompt,undefined=DebugUndefined).render(
            tools=tool_prompt,
            query=self.context.query,
            date=self.context.date_info,
            sopPrompt=self.context.sop_prompt,
            executorSopPrompt=sop_prompt
        )
        self.next_step_prompt=Template(next_step_prompt,undefined=DebugUndefined).render(
            tools=tool_prompt,
            query=self.context.query,
            date=self.context.date_info,
            sopPrompt=self.context.sop_prompt,
            executorSopPrompt=sop_prompt
        )
        self.system_prompt_snapshot=self.system_prompt
        self.next_step_prompt_snapshot=self.next_step_prompt
        
        self.printer=self.context.printer
        
        self.max_steps=orblite_config.orb_lite_planner.max_steps
        self.llm=LLM(orblite_config.orb_lite_executor.model_name)
        
        self.max_observe=orblite_config.orb_lite_executor.max_observe
        
        self.available_tools=self.context.tool_collection
        
        self.task_id=0
        
        return self
        
    async def think(self) -> bool:
        file_str=file_util.format_file_info(self.context.product_files,False)
        self.system_prompt=Template(self.system_prompt_snapshot,undefined=DebugUndefined).render(
            files=file_str,
        )
        self.next_step_prompt=Template(self.next_step_prompt_snapshot,undefined=DebugUndefined).render(
            files=file_str,
        )
        if self.memory and not self.memory.get_last_message().role==Role.USER:
            user_msg=Message.user_message(self.next_step_prompt)
            self.memory.add_message(user_msg)
        try:
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
                stream=False,
                timeout=300
            )
            tool_calls = (
                ask_result.tool_calls if ask_result and ask_result.tool_calls else []
            )
            self.tool_calls=[
                ToolCall(id=item.id,type=item.type,function=Function(name=item.function.name,arguments=item.function.arguments))
                for item in tool_calls
            ]
            if ask_result.content:
                if not tool_calls:
                    await self.printer.send(message_type="task_summary",message={
                        "taskSummary":ask_result.content,
                        "fileList":self.context.task_product_files
                    })
                else:
                    await self.printer.send(message_type="tool_thought",message=ask_result.content)

            if self.tool_calls:
                assistant_msg=Message.from_tool_calls(content=ask_result.content,tool_calls=tool_calls)
            else:
                assistant_msg=Message.assistant_message(content=ask_result.content)
            self.memory.add_message(assistant_msg)
        except ValueError:
            raise
        except Exception as e:
            if hasattr(e, "__cause__") and isinstance(e.__cause__, TokenLimitExceeded):
                token_limit_error = e.__cause__
                logger.error(
                    f"Token limit error (from RetryError): {token_limit_error}"
                )
                self.memory.add_message(
                    Message.assistant_message(
                        f"Maximum token limit reached, cannot continue execution: {str(token_limit_error)}"
                    )
                )
                self.state = AgentState.FINISHED
                return False
            raise
        
        return True
    
    
    async def act(self) -> str:
        if not self.tool_calls:
            self.state=AgentState.FINISHED
            if self.clear_tool_message:
                self.memory.clear_tool_context()
            return "当前task完成，请将当前task标记为 completed"
        tool_results={}
        for command in self.tool_calls:
            await self.printer.send(
                message_type="tool_start",
                message={
                    "toolName": command.function.name,
                    "toolParam": command.function.arguments,
                },
            )
            res=await self.execute_tool(command)
            tool_results[command.id]=res
            await self.printer.send(message_type="tool_result",message={
                    "toolName":command.function.name,
                    "toolParam":command.function.arguments,
                    "toolResult":res
            })
        
        results=[]
        for command in self.tool_calls:
            result=tool_results[command.id]
            result_str=json.dumps(result,ensure_ascii=False)
            result_str=result_str[:min(len(result_str),self.max_observe)]
            # 添加工具到记忆
            tool_msg=Message.tool_message(
                content=result,
                tool_call_id=command.id
            )
            self.memory.add_message(tool_msg)
            results.append(result_str)
        return "\n\n".join(results)

    async def run(self, query: str) -> None:
        query=pre_prompt+query
        self.context.task=query
        return await super().run(query)