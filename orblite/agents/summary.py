import re
from typing import Optional,List,Dict
from jinja2 import DebugUndefined, Template
from pydantic import Field, model_validator
from orblite.agents.base import BaseAgent
from orblite.agents.planning import orblite_config
from orblite.exceptions import OrbLiteError
from orblite.llm import LLM
from orblite.log_utils import logger
from orblite.prompts.summary import system_prompt
from orblite.schemas.agent_res import TaskSummaryResult
from orblite.schemas.base import AgentType
from orblite.schemas.message import Message


class SummaryAgent(BaseAgent):
    request_id:Optional[str]=Field(None,description="请求ID")
    message_size_limit:int=Field(1000,description="消息上下文长度限制大小")
    log_flag:str=Field("summaryTaskResult")
    
    @model_validator(mode="after")
    def post_init(self)->"SummaryAgent":
        self.name="abstracter"
        self.description="摘要生成智能体"
        self.system_prompt=system_prompt
        self.llm=LLM(orblite_config.orb_lite_planner.model_name if self.context.agent_type==AgentType.PLAN_SOLVE else orblite_config.orb_lite_executor.model_name)
        return self
    
    async def step(self) -> str:
        return ""
    
    async def run(self, query: str) -> None:
        raise RuntimeError("该方法不能被执行")
    
    def create_file_info(self):
        files=self.context.product_files
        if not files:
            return ""
        res=""
        for file in files:
            if not file.is_internal_file:
                res+=f"{file.file_name} : {file.description}\n"
        return res.strip()
    
    def format_system_prompt(self,task_history:str,query:str):
        system_prompt_tmp=self.system_prompt
        if not system_prompt_tmp:
            raise OrbLiteError("System prompt is not configured")
        return Template(system_prompt_tmp,undefined=DebugUndefined).render(
            taskHistory=task_history,
            query=query,
            fileNameDesc=self.create_file_info()
        )
    
    def create_system_message(self,content:str)->Message:
        return Message.user_message(content=content)
    
    
    def parse_llm_response(self,llm_response:str)->TaskSummaryResult:
        if not llm_response or llm_response.strip()=="":
            logger.error("pattern matcher failed for response is null")
            return TaskSummaryResult()

        parts1 = re.split(r'\$\$\$', llm_response)
    
        if len(parts1) < 2:
            return TaskSummaryResult(task_summary=parts1[0])
    
        summary = parts1[0]
        file_names = parts1[1]
    
        files = self.context.product_files
    
        if files:
            files=files[::-1]
        else:
            logger.error(f"requestId: {self.request_id} llmResponse:{llm_response} productFile list is empty")
            # 文件列表为空，交付物中不显示文件
            return TaskSummaryResult(task_summary=summary)
    
        # 匹配并收集相关文件
        product = []
        # 按中文顿号 "、" 分割文件名
        items = file_names.split("、")
    
        for item in items:
            trimmed_item = item.strip()
            # 跳过空项
            if not trimmed_item:
                continue
            # 在文件列表中查找匹配的文件
            for file in files:
                if file.file_name.strip() in trimmed_item:
                    product.append(file)
                    break
        return TaskSummaryResult(task_summary=summary, files=product)
    
    async def summary(self,messages:List[Message],query:str)->TaskSummaryResult:
        if not messages or not query:
            return TaskSummaryResult()
        try:
            task_history=""
            for message in messages:
                content=message.content
                if not content and len(content)>self.message_size_limit:
                    content=content[:self.message_size_limit]
                task_history+=f"role:{message.role} content:{content}\n"
            formatted_prompt=self.format_system_prompt(task_history,query)
            user_message=self.create_system_message(formatted_prompt)
            summary_response=await self.llm.ask(
                messages=[user_message],
                stream=False,
                temperature=0.01
            )
            return self.parse_llm_response(summary_response)
        except Exception as e:
            return TaskSummaryResult(task_summary=f"任务执行失败，请联系管理员！{e}")