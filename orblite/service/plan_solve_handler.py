import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from jinja2 import DebugUndefined, Template
from orblite.agents.executor import ExecutorAgent
from orblite.agents.planning import PlanningAgent, orblite_config
from orblite.agents.summary import SummaryAgent
from orblite.log_utils import logger
from orblite.schemas.agent_req import AgentRequest
from orblite.schemas.base import AgentType
from orblite.schemas.context import AgentContext
from orblite.service.base import AgentHandlerService



class PlanSolveHandler(AgentHandlerService):
    def support(self, context: AgentContext, request: AgentRequest) -> bool:
        return request.agent_type == AgentType.PLAN_SOLVE

    async def handle(self, agent_context: 'AgentContext', request: 'AgentRequest') -> str:
        # 2. 初始化 Agents
        planning = PlanningAgent(context=agent_context)
        executor = ExecutorAgent(context=agent_context)
        summary = SummaryAgent(context=agent_context)

        # 替换 Prompt 中的变量
        summary.system_prompt = Template(summary.system_prompt, undefined=DebugUndefined).render(
            query=request.query
        )

        await agent_context.printer.send(
            message_type="planning_start",
            message={"query": request.query},
        )
        planning_result = await planning.run(agent_context.query)
        plan_data = planning.planning_tool.plan.model_dump() if planning.planning_tool.plan else None
        await agent_context.printer.send(
            message_type="plan_updated",
            message={
                "plan": plan_data,
            },
        )
        step_idx = 0
        max_step_num = orblite_config.orb_lite_planner.max_steps
        while step_idx <= max_step_num:
            logger.info(f"\n{planning.planning_tool.get_format_plan()}\n")
            # 解析任务列表
            task = f"你的任务是：{planning_result.strip()}"

            await agent_context.printer.send(
                message_type="step_start",
                message={"stepIndex": step_idx + 1, "task": task},
            )
            agent_context.task_product_files = []
            executor_result = ""
            executor_result = await executor.run(task)
            await agent_context.printer.send(
                message_type="step_done",
                message={"stepIndex": step_idx + 1, "result": executor_result},
            )

            # 再次运行 planning 获取下一步指令或判断是否结束
            planning_result = await planning.run(executor_result)
            plan_data = planning.planning_tool.plan.model_dump() if planning.planning_tool.plan else None
            await agent_context.printer.send(
                message_type="plan_updated",
                message={
                    "plan": plan_data,
                },
            )

            # 检查任务是否完成
            if "finish" in planning_result:
                await self._handle_finish(agent_context, executor, summary, request)
                break

            # 状态检查
            # if planning.state == "IDLE" or executor.state == "IDLE":
            #     await agent_context.printer.send("result", "达到最大迭代次数，任务终止。")
            #     break
            if planning.state == "ERROR" or executor.state == "ERROR":
                await agent_context.printer.send(
                    message_type="error",
                    message="任务执行异常，请联系管理员，任务终止。",
                )
                break
            step_idx += 1

        return ""

    async def _handle_finish(self, context:AgentContext, executor:ExecutorAgent, summary:SummaryAgent, request:AgentRequest):
        """ 任务结束后的总结处理 """
        result = await summary.summary(executor.memory.messages, request.query)
        task_result = {"taskSummary": result.task_summary}

        if not result.files:
            if context.product_files:
                file_responses = list(context.product_files)
                # 过滤内部文件并反转
                file_responses = [f for f in file_responses if f and not f.is_internal_file]
                file_responses=file_responses[::-1]
                task_result["fileList"] = file_responses
        else:
            task_result["fileList"] = result.files

        await context.printer.send(
            message_type="product_files",
            message=task_result.get("fileList", []),
        )
        await context.printer.send(message_type="result", message=task_result)
        await context.printer.send(
            message_type="session_end",
            message={"status": "completed"},
            is_final=True,
        )