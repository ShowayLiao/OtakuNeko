import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler
from typing import Optional, Dict, Any

# 尝试导入并发日志处理器，如果不存在则使用标准处理器
try:
    from concurrent_log_handler import ConcurrentRotatingFileHandler
    HAS_CONCURRENT_HANDLER = True
except ImportError:
    HAS_CONCURRENT_HANDLER = False


class RequestContextFilter(logging.Filter):
    """请求上下文过滤器，用于添加请求ID到日志中"""
    def __init__(self):
        super().__init__()
        self.request_id = None
    
    def set_request_id(self, request_id: str):
        """设置请求ID"""
        self.request_id = request_id
    
    def clear_request_id(self):
        """清除请求ID"""
        self.request_id = None
    
    def filter(self, record):
        """向日志记录添加请求ID"""
        record.request_id = self.request_id or "-"
        return True


class LoggingConfig:
    """日志配置类"""
    
    def __init__(
        self,
        log_dir: str = "logs",
        log_level: str = "INFO",
        max_bytes: int = 104857600,  # 100MB
        backup_count: int = 30,  # 保留30天
        log_format: str = "%(asctime)s - %(levelname)s - %(module)s - %(request_id)s - %(message)s",
        date_format: str = "%Y-%m-%d %H:%M:%S",
    ):
        """
        初始化日志配置
        
        Args:
            log_dir: 日志文件目录
            log_level: 日志级别
            max_bytes: 单个日志文件最大字节数
            backup_count: 保留的日志文件数量
            log_format: 日志格式
            date_format: 日期格式
        """
        self.log_dir = log_dir
        self.log_level = log_level
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.log_format = log_format
        self.date_format = date_format
        self.request_filter = RequestContextFilter()
        
        # 确保日志目录存在
        self._ensure_log_dir()
    
    def _ensure_log_dir(self):
        """确保日志目录存在"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)
    
    def get_logger(self, name: str = None) -> logging.Logger:
        """
        获取配置好的日志记录器
        
        Args:
            name: 日志记录器名称
        
        Returns:
            配置好的日志记录器
        """
        logger = logging.getLogger(name)
        logger.setLevel(self.log_level)
        
        # 清除已有的处理器，避免重复
        if logger.handlers:
            logger.handlers.clear()
        
        # 添加控制台处理器（仅用于开发环境）
        if os.getenv("DEBUG", "False").lower() == "true":
            console_handler = logging.StreamHandler()
            console_handler.setLevel(self.log_level)
            console_formatter = logging.Formatter(self.log_format, self.date_format)
            console_handler.setFormatter(console_formatter)
            console_handler.addFilter(self.request_filter)
            logger.addHandler(console_handler)
        
        # 添加文件处理器
        file_handler = self._create_file_handler("app")
        logger.addHandler(file_handler)
        
        # 添加错误日志处理器
        error_handler = self._create_file_handler("error", logging.ERROR)
        logger.addHandler(error_handler)
        
        # 避免日志传播
        logger.propagate = False
        
        return logger
    
    def _create_file_handler(self, log_name: str, level: int = logging.DEBUG) -> logging.Handler:
        """
        创建文件处理器
        
        Args:
            log_name: 日志文件名前缀
            level: 日志级别
        
        Returns:
            配置好的文件处理器
        """
        log_file = os.path.join(self.log_dir, f"{log_name}.log")
        
        if HAS_CONCURRENT_HANDLER:
            # 使用并发日志处理器（异步写入）
            handler = ConcurrentRotatingFileHandler(
                log_file,
                maxBytes=self.max_bytes,
                backupCount=self.backup_count,
                encoding="utf-8"
            )
        else:
            # 使用时间轮转处理器作为备选
            handler = TimedRotatingFileHandler(
                log_file,
                when="midnight",
                interval=1,
                backupCount=self.backup_count,
                encoding="utf-8"
            )
        
        handler.setLevel(level)
        formatter = logging.Formatter(self.log_format, self.date_format)
        handler.setFormatter(formatter)
        handler.addFilter(self.request_filter)
        
        return handler
    
    def set_request_id(self, request_id: str):
        """
        设置请求ID
        
        Args:
            request_id: 请求ID
        """
        self.request_filter.set_request_id(request_id)
    
    def clear_request_id(self):
        """清除请求ID"""
        self.request_filter.clear_request_id()


# 全局日志配置实例
logging_config = LoggingConfig()


def get_logger(name: str = None) -> logging.Logger:
    """
    获取日志记录器的便捷函数
    
    Args:
        name: 日志记录器名称
    
    Returns:
        配置好的日志记录器
    """
    return logging_config.get_logger(name)


def set_request_id(request_id: str):
    """
    设置请求ID的便捷函数
    
    Args:
        request_id: 请求ID
    """
    logging_config.set_request_id(request_id)


def clear_request_id():
    """清除请求ID的便捷函数"""
    logging_config.clear_request_id()