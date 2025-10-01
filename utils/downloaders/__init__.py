"""
下载器模块初始化文件
"""

import logging
from typing import Optional, Dict, Any
from config import Config

# 设置日志记录器
logger = logging.getLogger(__name__)

# 导入基础下载器类，供类型注解使用
from .base import Downloader, DownloadQuality
from .bilibili_downloader import BilibiliDownloader
from .factory import DownloaderFactory

__all__ = ['Downloader', 'DownloadQuality', 'BilibiliDownloader', 'DownloaderFactory']