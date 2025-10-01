"""
下载器基类模块

定义视频下载器的通用接口和基本功能
"""

import os
from abc import ABC, abstractmethod
from typing import Union, Optional, Dict, Any, Literal

# 下载质量类型定义
DownloadQuality = Literal["fast", "medium", "high"]

# 质量映射表
QUALITY_MAP = {
    "fast": "64k",    # 低质量，快速下载
    "medium": "128k", # 中等质量
    "high": "192k"    # 高质量
}

class DownloadResult:
    """下载结果类"""
    
    def __init__(
        self,
        file_path: str,
        title: str,
        duration: int,
        cover_url: str,
        platform: str,
        video_id: str,
        raw_info: Dict[str, Any] = None
    ):
        self.file_path = file_path      # 文件路径
        self.title = title              # 视频标题
        self.duration = duration        # 视频时长(秒)
        self.cover_url = cover_url      # 封面URL
        self.platform = platform        # 平台名称
        self.video_id = video_id        # 视频ID
        self.raw_info = raw_info or {}  # 原始信息

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "file_path": self.file_path,
            "title": self.title,
            "duration": self.duration,
            "cover_url": self.cover_url,
            "platform": self.platform,
            "video_id": self.video_id
        }

class Downloader(ABC):
    """下载器基类"""
    
    def __init__(self):
        """初始化下载器"""
        # 缓存目录
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "cache")
        
        # 创建缓存目录
        os.makedirs(self.cache_dir, exist_ok=True)
    
    @abstractmethod
    def download_audio(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast"
    ) -> DownloadResult:
        """
        下载视频的音频部分
        
        Args:
            video_url: 视频URL
            output_dir: 输出目录，默认为缓存目录
            quality: 下载质量，可选值为"fast"、"medium"、"high"
            
        Returns:
            DownloadResult: 下载结果对象
        """
        pass
    
    @abstractmethod
    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "medium"
    ) -> DownloadResult:
        """
        下载完整视频
        
        Args:
            video_url: 视频URL
            output_dir: 输出目录，默认为缓存目录
            quality: 下载质量，可选值为"fast"、"medium"、"high"
            
        Returns:
            DownloadResult: 下载结果对象
        """
        pass
    
    @abstractmethod
    def extract_info(self, video_url: str) -> Dict[str, Any]:
        """
        提取视频信息，不下载
        
        Args:
            video_url: 视频URL
            
        Returns:
            Dict: 视频信息字典
        """
        pass
    
    def get_output_dir(self, output_dir: Union[str, None] = None) -> str:
        """
        获取输出目录
        
        Args:
            output_dir: 指定的输出目录，如果为None则使用缓存目录
            
        Returns:
            str: 输出目录路径
        """
        if output_dir is None:
            output_dir = self.cache_dir
        os.makedirs(output_dir, exist_ok=True)
        return output_dir