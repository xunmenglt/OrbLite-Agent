from typing import Optional
from pydantic import BaseModel


class File(BaseModel):
    # 使用 Optional 处理可能为 null 的字段，或者直接定义类型（如果不允许为 None）
    oss_url: Optional[str] = None
    domain_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    description: Optional[str] = None
    origin_file_name: Optional[str] = None
    origin_oss_url: Optional[str] = None
    origin_domain_url: Optional[str] = None
    is_internal_file: bool = False  

    class Config:
        # 如果你希望像 Java 那样通过驼峰命名法(JSON)交互，但 Python 内部用蛇形命名
        # 可以开启如下配置（需配合 Field 使用 alias）
        populate_by_name = True