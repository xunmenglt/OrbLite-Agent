from typing import Optional,List
from pydantic import BaseModel, Field

from orblite.utils.file_util import File


class TaskSummaryResult(BaseModel):
    task_summary:Optional[str]=Field("")
    files:List[File]=Field(default_factory=list)