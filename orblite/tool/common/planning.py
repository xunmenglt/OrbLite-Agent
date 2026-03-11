# tool/planning.py
from cgitb import handler
import this
from typing import Dict, List, Literal, Optional,Any

from pydantic import BaseModel, Field
from orblite.exceptions import OrbLiteError, ToolError
from orblite.tool.base import BaseTool, ToolResult
from orblite.prompts.tool import plan_tool_desc_prompt


class Plan(BaseModel):
    title:str=Field("",description="任务标题")
    steps:List[str]=Field(default_factory=list,description="子任务列表")
    step_status:List[str]=Field(default_factory=list,description="子任务状态")
    notes:List[str]=Field(default_factory=list,description="子任务备注列表")
    
    
    @staticmethod
    def create(title:str,steps:List[str])->"Plan":
        status=["not_started"]*len(steps)
        notes=[""]*len(steps)
        return Plan(
            title=title,
            steps=steps,
            step_status=status,
            notes=notes
        )
    
    def update(self,title:str,new_steps:List[str]):
        if self.title:
            self.title=title
        if new_steps:
            new_status=[]
            new_notes=[]
            for i in range(len(new_steps)):
                if i<len(self.steps) and new_steps[i]==self.steps[i]:
                    new_status.append(self.step_status[i])
                    new_notes.append(self.notes[i])
                else:
                    new_status.append("not_started")
                    new_notes.append("")
            self.steps=new_steps
            self.notes=new_notes
            self.step_status=new_status
            
    
    def update_step_status(self,step_index:int,status:str,note:str=None):
        if step_index<0 and step_index>=len(self.steps):
            raise RuntimeError(f"Invalid step index: {step_index}")
        if status:
            self.step_status[step_index]=status
            
        if note:
            self.notes[step_index]=note
    
    def get_current_step(self)->str:
        for i in range(len(self.steps)):
            if "in_progress"==self.step_status[i]:
                return self.steps[i]
        return ""
    
    def step_plan(self)->None:
        if not self.steps:
            return
        if not self.get_current_step():
            self.update_step_status(0,"in_progress","")
            return
        for i in range(len(self.steps)):
            if "in_progress"==self.step_status[i]:
                self.update_step_status(i,"completed","")
                if i+1<len(self.steps):
                    self.update_step_status(i+1,"in_progress","")
                    break
    
    def format(self) -> str:
        """
        格式化计划显示，对应 Java 的 format() 方法
        """
        lines = []
        # 添加计划标题
        lines.append(f"Plan: {self.title}")
        # 添加步骤列表标题
        lines.append("Steps:")
        
        for i, (step, status) in enumerate(zip(self.steps, self.step_status)):
            # 注意：Java 是 i+1，status 来源于列表
            status_symbol = {
                "not_started": "[ ]",
                "in_progress": "[→]",
                "completed": "[✓]",
                "blocked": "[!]",
            }.get(status, "[ ]")
            lines.append(f"{i + 1}. [{status_symbol}] {step}")
            
            # 获取对应的备注
            if i < len(self.notes) and self.notes[i]:
                lines.append(f"   Notes: {self.notes[i]}")
        
        return "\n".join(lines)
        



class PlanningTool(BaseTool):
    """
    一个规划工具，允许智能体创建和管理解决复杂任务的计划。
    该工具提供了创建计划、更新计划步骤和跟踪进度的功能。
    """

    name: str = "planning"
    description: str = plan_tool_desc_prompt
    parameters: dict = {"type":"object","properties":{"step_status":{"description":"每一个子任务的状态. 当command是 mark_step 时使用.","type":"string","enum":["not_started","in_progress","completed","blocked"]},"step_notes":{"description":"每一个子任务的的备注，当command 是 mark_step 时，是备选参数。","type":"string"},"step_index":{"description":"当command 是 mark_step 时，是必填参数.","type":"integer"},"title":{"description":"任务的标题，当command是create时，是必填参数，如果是update 则是选填参数。","type":"string"},"steps":{"description":"入参是任务列表. 当创建任务时，command是create，此时这个参数是必填参数。任务列表的的格式如下：[\"执行顺序 + 编号、执行任务简称：执行任务的细节描述\"]。不同的子任务之间不能重复、也不能交叠，可以收集多个方面的信息，收集信息、查询数据等此类多次工具调用，是可以并行的任务。具体的格式示例如下：- 任务列表示例1: [\"执行顺序1. 执行任务简称（不超过6个字）：执行任务的细节描述（不超过50个字）\", \"执行顺序2. xxx（不超过6个字）：xxx（不超过50个字）, ...\"]；","type":"array","items":{"type":"string"}},"command":{"description":"需要执行的命令，取值范围是: create","type":"string","enum":["create"]}},"required":["command"]}
    plan:Optional[Plan]=Field(default=None)
    
    
    async def execute(self, **kwargs) -> ToolResult:
        command=kwargs.get("command")
        if not command:
            raise OrbLiteError("Command is required")
        command_handlers={
            "create":self.create_plan,
            "update":self.update_plan,
            "mark_step":self.mark_step,
            "finish":self.finish_plan
        }
        handler=command_handlers.get(command)
        if handler:
            return handler(**kwargs)
        else:
            raise OrbLiteError(f"Unknown command: {command}")
        
        
    def create_plan(self,title:str,steps:List[str]=[],**kwargs)->ToolResult:
        if not title or not steps:
            raise OrbLiteError("title, and steps are required for create command")
        if self.plan:
            raise OrbLiteError("A plan already exists. Delete the current plan first.")
        self.plan=Plan.create(title=title,steps=steps)
        return ToolResult(output="我已创建plan")
    
    def update_plan(self,title:str,steps:List[str]=[],**kwargs)->str:
        if not self.plan:
            raise OrbLiteError("No plan exists. Create a plan first.")
        self.plan.update(title, steps)
        return ToolResult(output="我已更新plan")
    
    def mark_step(self,step_index:int,step_status:str,step_note:str,**kwargs)->str:
        if not self.plan:
            raise OrbLiteError("No plan exists. Create a plan first.")
        if step_index is None:
            raise OrbLiteError("step_index is required for mark_step command")
        self.plan.update_step_status(step_index,step_status,step_note)
        return ToolResult(output=f"我已标记plan {step_index} 为 {step_status}")
    
    def finish_plan(self)->ToolResult:
        if not self.plan:
            self.plan=Plan()
        else:
            for i in range(len(self.plan.steps)):
                self.plan.update_step_status(i,"completed","")
        
        return ToolResult(output="我已更新plan为完成状态")
    
    
    def step_plan(self):
        self.plan.step_plan()
    
    
    def get_format_plan(self)->str:
        if not self.plan:
            return "目前还没有Plan"
        return self.plan.format()
    
                
    