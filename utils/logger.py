#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志管理模块
提供项目统一的日志配置和管理功能
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器（仅在控制台输出时使用）"""
    
    # 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
        'RESET': '\033[0m'      # 重置
    }
    
    def format(self, record):
        # 添加颜色
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        
        return super().format(record)


class Logger:
    """统一日志管理器"""
    
    def __init__(self, name: str = None):
        self.name = name or __name__
        self.logger = logging.getLogger(self.name)
        self._configured = False
    
    def setup_logger(self, 
                    level: int = logging.INFO,
                    log_file: Optional[str] = None,
                    max_file_size: int = 10 * 1024 * 1024,  # 10MB
                    backup_count: int = 5,
                    console_output: bool = True,
                    file_output: bool = True) -> logging.Logger:
        """
        配置日志记录器
        
        Args:
            level: 日志级别
            log_file: 日志文件路径
            max_file_size: 单个日志文件最大大小（字节）
            backup_count: 保留的日志文件备份数量
            console_output: 是否输出到控制台
            file_output: 是否输出到文件
            
        Returns:
            logging.Logger: 配置好的日志记录器
        """
        if self._configured:
            return self.logger
        
        # 设置日志级别
        self.logger.setLevel(level)
        
        # 创建格式化器
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # 控制台处理器
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
        
        # 文件处理器
        if file_output:
            if not log_file:
                # 默认日志文件路径
                log_dir = os.path.join(os.getcwd(), 'logs')
                os.makedirs(log_dir, exist_ok=True)
                log_file = os.path.join(log_dir, f'{self.name}.log')
            
            # 确保日志目录存在
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            
            # 使用RotatingFileHandler实现日志轮转
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
        
        self._configured = True
        return self.logger
    
    def get_logger(self) -> logging.Logger:
        """获取日志记录器"""
        if not self._configured:
            self.setup_logger()
        return self.logger


# 全局日志管理器实例
_loggers = {}


def get_logger(name: str = None, **kwargs) -> logging.Logger:
    """
    获取或创建日志记录器
    
    Args:
        name: 日志记录器名称
        **kwargs: 传递给setup_logger的参数
        
    Returns:
        logging.Logger: 日志记录器
    """
    if name is None:
        # 获取调用者的模块名
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'unknown')
    
    if name not in _loggers:
        logger_manager = Logger(name)
        logger_manager.setup_logger(**kwargs)
        _loggers[name] = logger_manager
    
    return _loggers[name].get_logger()


def setup_project_logging(level: int = logging.INFO, 
                         log_dir: str = 'logs',
                         console_output: bool = True):
    """
    设置项目级别的日志配置
    
    Args:
        level: 日志级别
        log_dir: 日志目录
        console_output: 是否输出到控制台
    """
    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
    
    # 主应用日志
    app_logger = get_logger('app', 
                           level=level,
                           log_file=os.path.join(log_dir, 'app.log'),
                           console_output=console_output)
    
    # API日志
    api_logger = get_logger('bilibili_api',
                           level=level,
                           log_file=os.path.join(log_dir, 'api.log'),
                           console_output=console_output)
    
    # 下载器日志
    downloader_logger = get_logger('downloader',
                                  level=level,
                                  log_file=os.path.join(log_dir, 'downloader.log'),
                                  console_output=console_output)
    
    # 错误日志（单独文件）
    error_logger = get_logger('error',
                             level=logging.ERROR,
                             log_file=os.path.join(log_dir, 'error.log'),
                             console_output=console_output)
    
    return {
        'app': app_logger,
        'api': api_logger,
        'downloader': downloader_logger,
        'error': error_logger
    }


class LoggerMixin:
    """日志记录器混入类"""
    
    @property
    def logger(self) -> logging.Logger:
        """获取当前类的日志记录器"""
        if not hasattr(self, '_logger'):
            class_name = self.__class__.__name__
            self._logger = get_logger(f"{self.__class__.__module__}.{class_name}")
        return self._logger


# 日志装饰器
def log_function_call(level: int = logging.DEBUG, 
                     include_args: bool = False,
                     include_result: bool = False):
    """
    记录函数调用的装饰器
    
    Args:
        level: 日志级别
        include_args: 是否包含参数信息
        include_result: 是否包含返回结果
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            
            # 记录函数调用开始
            if include_args:
                logger.log(level, f"调用函数 {func.__name__}，参数: args={args}, kwargs={kwargs}")
            else:
                logger.log(level, f"调用函数 {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                
                # 记录函数调用成功
                if include_result:
                    logger.log(level, f"函数 {func.__name__} 执行成功，返回: {result}")
                else:
                    logger.log(level, f"函数 {func.__name__} 执行成功")
                
                return result
                
            except Exception as e:
                # 记录函数调用异常
                logger.error(f"函数 {func.__name__} 执行失败: {str(e)}", exc_info=True)
                raise
        
        return wrapper
    return decorator


# 性能监控装饰器
def log_performance(threshold_seconds: float = 1.0):
    """
    记录函数执行时间的装饰器
    
    Args:
        threshold_seconds: 超过此时间阈值才记录日志
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            import time
            logger = get_logger(func.__module__)
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                if execution_time > threshold_seconds:
                    logger.warning(f"函数 {func.__name__} 执行时间较长: {execution_time:.2f}秒")
                else:
                    logger.debug(f"函数 {func.__name__} 执行时间: {execution_time:.2f}秒")
                
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"函数 {func.__name__} 执行失败 (耗时 {execution_time:.2f}秒): {str(e)}")
                raise
        
        return wrapper
    return decorator


# 便捷函数
def debug(message: str, logger_name: str = None):
    """记录调试信息"""
    get_logger(logger_name).debug(message)


def info(message: str, logger_name: str = None):
    """记录信息"""
    get_logger(logger_name).info(message)


def warning(message: str, logger_name: str = None):
    """记录警告"""
    get_logger(logger_name).warning(message)


def error(message: str, logger_name: str = None, exc_info: bool = False):
    """记录错误"""
    get_logger(logger_name).error(message, exc_info=exc_info)


def critical(message: str, logger_name: str = None):
    """记录严重错误"""
    get_logger(logger_name).critical(message)


# 初始化项目日志
if __name__ != '__main__':
    # 自动设置项目日志（仅在被导入时）
    setup_project_logging()