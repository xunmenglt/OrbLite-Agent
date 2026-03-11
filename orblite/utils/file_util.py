
from typing import List
from orblite.schemas.file import File




def format_file_info(files:List[File],filter_internal_file:bool=False):
    res=""
    for file in files:
        if filter_internal_file and file.is_internal_file:
            continue
        file_url=file.origin_oss_url
        if not file_url:
            file_url=file.oss_url
            
        res+=f"fileName:{file.file_name} fileDesc:{file.description} fileUrl:{file_url}\n"
        return res