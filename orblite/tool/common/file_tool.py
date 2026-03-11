import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import Field

from orblite.schemas.context import AgentContext
from orblite.schemas.file import File
from orblite.tool.base import BaseTool, ToolResult
from orblite.config import config

WORKSPACE_ROOT=config.root_path / "file_tmp_dir"

class FileTool(BaseTool):
    """
    文件工具：保存文件、查看文件描述、读取文件内容
    """

    name: str = "file_tool"
    description: str = "传入文件名称进行保存文件、查看文件描述信息、读取文件内容"
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "description": "文件操作类型枚举值包含upload、get和read三种操作命令:，含义分别是upload：表示存储文件信息，get：表示根据文件名获取文件描述信息，read：表示根据文件名读取文件内容",
                "type": "string",
                "enum": ["upload", "get", "read"],
            },
            "filename": {"description": "文件名一定是中文名称，文件名后缀取决于准备写入的文件内容，如果内容是Markdown格式排版的内容，则文件名的后缀是.md结尾。读取文件时，一定是历史对话中已经写入的文件名称。所有文件名称都需要唯一。文件名称中不能使用特殊符号，不能使用、，？等符号，如果需要，可以使用下划线_。需要写入数据表格类的文件时，以 .csv 文件为后缀。纯文本文件优先使用 Markdown 文件保存，不要使用 .txt 保存文件。不支持.pdf、.png、.zip为后缀的文件读写。", "type": "string"},
            "description": {"description": "文件描述，用20字左右概括该文件内容的主要内容及用途，当command是upload时，属于必填参数", "type": "string"},
            "is_internal_file": {"description":"文件是否是阶段性重要成果和最终结果标识，如果该文件最终是需要给用户查收的需要设置为false，方便中途智能体查看的设为true。当command是upload时，属于必填参数","type":"boolean"},
            "content": {"description": "这是需要写入的文件内容，当command是upload时，属于必填参数。", "type": "string"},
            
        },
        "required": ["command", "filename"],
    }

    agent_context: Optional[AgentContext] = Field(default=None, exclude=True)
    base_dir: Path = WORKSPACE_ROOT

    async def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get("command")
        if not command:
            return self._fail_response("command 不能为空")
        handler_map = {
            "upload": self._upload_file,
            "get": self._get_file_info,
            "read": self._read_file,
        }
        handler = handler_map.get(command)
        if not handler:
            return self._fail_response(f"未知命令: {command}")
        return handler(**kwargs)

    def _upload_file(self, filename: str, description: str = "", content: str = "",is_internal_file:bool=False, **kwargs) -> ToolResult:
        if not filename:
            return self._fail_response("filename 不能为空")
        if content is None:
            return self._fail_response("content 不能为空")
        file_path = self._get_file_path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        metadata = self._load_metadata()
        metadata[filename] = {"description": description}
        self._save_metadata(metadata)
        end_file=File(
            file_name=filename,
            description=description,
            is_internal_file=is_internal_file
        )
        self.agent_context.product_files.append(end_file)
        if not is_internal_file:
            self.agent_context.task_product_files.append(end_file)
        if self.agent_context and self.agent_context.printer:
            files_payload = [f.model_dump() for f in self.agent_context.task_product_files]
            asyncio.create_task(
                self.agent_context.printer.send(
                    message_type="product_files",
                    message=files_payload,
                )
            )
        return self._success_response({"status": "success", "data": {"filename": filename}})

    def _get_file_info(self, filename: str, **kwargs) -> ToolResult:
        if not filename:
            return self._fail_response("filename 不能为空")
        metadata = self._load_metadata()
        info = metadata.get(filename)
        if not info:
            return self._fail_response(f"未找到文件描述信息: {filename}")
        return self._success_response(
            {
                "status": "success",
                "msg": "获取成功",
                "data": {"filename": filename, "description": info.get("description", "")},
            }
        )

    def _read_file(self, filename: str, **kwargs) -> ToolResult:
        if not filename:
            return self._fail_response("filename 不能为空")
        file_path = self._get_file_path(filename)
        if not file_path.exists():
            return self._fail_response(f"未找到文件: {filename}")
        content = file_path.read_text(encoding="utf-8")
        return self._success_response(
            {
                "status": "success",
                "msg": "读取成功",
                "data": {"filename": filename, "content": content},
            }
        )

    def _get_file_path(self, filename: str) -> Path:
        return self._get_request_dir() / filename

    def _get_request_dir(self) -> Path:
        request_id = "default"
        if self.agent_context and self.agent_context.request_id:
            request_id = self.agent_context.request_id
        base_dir = self.base_dir or self._default_base_dir()
        return base_dir / request_id

    def _default_base_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "runtime" / "files"

    def _metadata_path(self) -> Path:
        return self._get_request_dir() / "metadata.json"

    def _load_metadata(self) -> Dict[str, Dict[str, Any]]:
        path = self._metadata_path()
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _save_metadata(self, metadata: Dict[str, Dict[str, Any]]) -> None:
        path = self._metadata_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(metadata, file, ensure_ascii=False, indent=2)

    def _success_response(self, data: Dict[str, Any]) -> ToolResult:
        return ToolResult(output=json.dumps(data, ensure_ascii=False))

    def _fail_response(self, msg: str) -> ToolResult:
        return ToolResult(output=json.dumps({"status": "fail", "msg": msg}, ensure_ascii=False))
