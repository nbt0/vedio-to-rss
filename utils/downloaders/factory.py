"""
下载器工厂模块

负责创建和管理不同平台的下载器实例
"""

import logging
from typing import Dict, Optional, Type

from .base import Downloader
from .bilibili_downloader import BilibiliDownloader
from config import Config

# 设置日志记录器
logger = logging.getLogger(__name__)

class DownloaderFactory:
    """下载器工厂类"""
    
    # 平台与下载器类的映射
    _downloaders: Dict[str, Type[Downloader]] = {
        "bilibili": BilibiliDownloader,
        # 未来可以添加更多平台
    }
    
    @classmethod
    def get_downloader(cls, platform: str, config=None) -> Optional[Downloader]:
        """
        获取指定平台的下载器实例
        
        Args:
            platform: 平台名称，如"bilibili"、"youtube"等
            config: 配置对象，传递给下载器构造函数
            
        Returns:
            Downloader: 下载器实例，如果平台不支持则返回None
        """
        downloader_class = cls._downloaders.get(platform.lower())
        if downloader_class:
            # 修复参数错误：如果config为None，则不传递参数
            if config is not None:
                return downloader_class(config)
            else:
                return downloader_class()
        return None
    
    @classmethod
    def create_downloader_for_url(cls, url: str, config=None) -> Optional[Downloader]:
        """
        根据URL创建合适的下载器
        
        Args:
            url: 视频URL
            config: 配置对象
            
        Returns:
            Downloader: 下载器实例，如果无法确定平台则返回None
        """
        # 记录日志
        logger.info(f"为URL创建下载器: {url}")
        
        # 根据URL选择合适的平台
        platform = cls._get_platform_from_url(url)
        
        if platform != "unknown":
            logger.info(f"使用{platform}下载器")
            return cls.get_downloader(platform, config)
        
        # 默认返回None表示不支持
        logger.warning(f"不支持的URL: {url}")
        return None
    
    @staticmethod
    def _get_platform_from_url(url: str) -> str:
        """
        从URL获取平台名称
        
        Args:
            url: 视频URL
            
        Returns:
            str: 平台名称
        """
        if "bilibili.com" in url or "b23.tv" in url:
            return "bilibili"
        elif "youtube.com" in url or "youtu.be" in url:
            return "youtube"
        elif "douyin.com" in url or "v.douyin.com" in url:
            return "douyin"
        else:
            return "unknown"
    
    @classmethod
    def register_downloader(cls, platform: str, downloader_class: Type[Downloader]):
        """
        注册新的下载器类
        
        Args:
            platform: 平台名称
            downloader_class: 下载器类
        """
        cls._downloaders[platform.lower()] = downloader_class
    
    @classmethod
    def get_supported_platforms(cls) -> list:
        """
        获取所有支持的平台列表
        
        Returns:
            list: 支持的平台名称列表
        """
        return list(cls._downloaders.keys())