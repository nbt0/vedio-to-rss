#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一异常处理模块
定义项目中使用的自定义异常类
"""


class VideoParseError(Exception):
    """视频解析错误"""
    def __init__(self, message: str, url: str = None):
        self.message = message
        self.url = url
        super().__init__(self.message)
    
    def __str__(self):
        if self.url:
            return f"视频解析错误 [{self.url}]: {self.message}"
        return f"视频解析错误: {self.message}"


class APIError(Exception):
    """API调用错误"""
    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)
    
    def __str__(self):
        if self.status_code:
            return f"API调用错误 [HTTP {self.status_code}]: {self.message}"
        return f"API调用错误: {self.message}"


class BilibiliAPIError(APIError):
    """B站API专用错误"""
    def __init__(self, message: str, code: int = None, **kwargs):
        self.code = code
        super().__init__(message, **kwargs)
    
    def __str__(self):
        if self.code:
            return f"B站API错误 [Code {self.code}]: {self.message}"
        return f"B站API错误: {self.message}"


class WBIEncryptionError(Exception):
    """WBI加密错误"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
    
    def __str__(self):
        return f"WBI加密错误: {self.message}"


class VideoDownloadError(Exception):
    """视频下载错误"""
    def __init__(self, message: str, url: str = None, error_code: str = None):
        self.message = message
        self.url = url
        self.error_code = error_code
        super().__init__(self.message)
    
    def __str__(self):
        if self.url and self.error_code:
            return f"视频下载错误 [{self.error_code}] [{self.url}]: {self.message}"
        elif self.url:
            return f"视频下载错误 [{self.url}]: {self.message}"
        return f"视频下载错误: {self.message}"


class CacheError(Exception):
    """缓存操作错误"""
    def __init__(self, message: str, cache_key: str = None):
        self.message = message
        self.cache_key = cache_key
        super().__init__(self.message)
    
    def __str__(self):
        if self.cache_key:
            return f"缓存错误 [{self.cache_key}]: {self.message}"
        return f"缓存错误: {self.message}"


class ConfigError(Exception):
    """配置错误"""
    def __init__(self, message: str, config_key: str = None):
        self.message = message
        self.config_key = config_key
        super().__init__(self.message)
    
    def __str__(self):
        if self.config_key:
            return f"配置错误 [{self.config_key}]: {self.message}"
        return f"配置错误: {self.message}"


class NetworkError(Exception):
    """网络连接错误"""
    def __init__(self, message: str, url: str = None, timeout: bool = False):
        self.message = message
        self.url = url
        self.timeout = timeout
        super().__init__(self.message)
    
    def __str__(self):
        error_type = "网络超时" if self.timeout else "网络错误"
        if self.url:
            return f"{error_type} [{self.url}]: {self.message}"
        return f"{error_type}: {self.message}"


class RSSGenerationError(Exception):
    """RSS生成错误"""
    def __init__(self, message: str, feed_data: dict = None):
        self.message = message
        self.feed_data = feed_data
        super().__init__(self.message)
    
    def __str__(self):
        return f"RSS生成错误: {self.message}"


# 异常处理装饰器
def handle_exceptions(default_return=None, log_error=True):
    """
    异常处理装饰器
    
    Args:
        default_return: 发生异常时的默认返回值
        log_error: 是否记录错误日志
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"函数 {func.__name__} 执行出错: {str(e)}", exc_info=True)
                
                # 如果是自定义异常，重新抛出
                if isinstance(e, (VideoParseError, APIError, BilibiliAPIError, 
                                WBIEncryptionError, VideoDownloadError, CacheError,
                                ConfigError, NetworkError, RSSGenerationError)):
                    raise e
                
                return default_return
        return wrapper
    return decorator


# 异常信息格式化
def format_exception_info(exception: Exception) -> dict:
    """
    格式化异常信息为字典
    
    Args:
        exception: 异常对象
        
    Returns:
        dict: 格式化后的异常信息
    """
    return {
        'type': type(exception).__name__,
        'message': str(exception),
        'details': getattr(exception, '__dict__', {})
    }