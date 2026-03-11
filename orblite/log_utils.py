"""
全局配置模块
提供全局日志对象和其他共享配置
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m'        # 重置
    }
    
    def format(self, record):
        # 为日志级别添加颜色
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        
        # 格式化消息
        message = super().format(record)
        
        return message


def setup_logger(
    name: str = "KP-MAM",
    log_dir: str = "logs",
    log_file: str = None,
    level: int = logging.INFO,
    console_output: bool = True,
    file_output: bool = True,
    colored: bool = True
) -> logging.Logger:
    """
    设置并返回配置好的日志对象
    
    Args:
        name: 日志器名称
        log_dir: 日志文件保存目录
        log_file: 日志文件名（如果为None，则使用时间戳自动生成）
        level: 日志级别
        console_output: 是否输出到控制台
        file_output: 是否输出到文件
        colored: 控制台输出是否使用彩色
    
    Returns:
        配置好的Logger对象
    """
    # 创建logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    
    # 清除已有的处理器（防止重复添加）
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # 日志格式
    log_format = "%(asctime)s|%(levelname)-8s|%(name)s|%(filename)s:%(lineno)d|%(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        
        if colored and sys.stdout.isatty():
            # 如果是终端且需要彩色输出
            console_formatter = ColoredFormatter(log_format, datefmt=date_format)
        else:
            console_formatter = logging.Formatter(log_format, datefmt=date_format)
        
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # 文件处理器
    if file_output:
        # 创建日志目录
        log_dir_path = Path(log_dir)
        log_dir_path.mkdir(parents=True, exist_ok=True)
        
        # 生成日志文件名
        if log_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = f"{name}_{timestamp}.log"
        
        log_file_path = log_dir_path / log_file
        
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(log_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # 记录日志文件位置
        logger.info(f"日志文件保存至: {log_file_path.absolute()}")
    
    return logger


def get_rank_logger(name: str = "orblite", rank: int = None) -> logging.Logger:
    """
    获取支持分布式训练rank的日志对象
    
    Args:
        name: 日志器名称
        rank: 分布式训练的进程rank，如果为None则自动检测
    
    Returns:
        Logger对象
    """
    # 尝试获取分布式训练的rank
    if rank is None:
        rank = int(os.environ.get('RANK', -1))
        local_rank = int(os.environ.get('LOCAL_RANK', -1))
        
        if rank == -1:
            rank = local_rank
    
    # 只在主进程或非分布式环境下输出日志到控制台
    console_output = (rank == -1 or rank == 0)
    
    # 所有进程都输出到文件，但文件名包含rank信息
    if rank > 0:
        log_file = f"{name}_rank{rank}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    else:
        log_file = None
    
    logger = setup_logger(
        name=name,
        log_file=log_file,
        console_output=console_output,
        file_output=True
    )
    
    if rank > 0:
        logger.info(f"初始化Rank {rank}的日志系统")
    
    return logger

logger=get_rank_logger()
# 导出接口
__all__ = ['setup_logger', 'get_rank_logger',"logger"]
