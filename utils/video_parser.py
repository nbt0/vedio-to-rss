# -*- coding: utf-8 -*-
"""
视频解析模块

这个模块负责：
1. 使用yt-dlp解析各种视频平台的URL
2. 提取视频信息（标题、时长、UP主等）
3. 处理B站分P视频的特殊逻辑
4. 获取音频文件的直链URL

注意：此模块的核心功能已迁移到utils.downloaders和utils.video_downloader模块
此模块保留是为了向后兼容，新代码应直接使用VideoDownloader类
"""

import re
import logging
from typing import Dict, List, Optional, Union
from urllib.parse import urlparse

# 导入新的下载器模块
from .video_downloader import VideoDownloader

class VideoParser:
    """
    视频解析器类
    
    注意：此类的核心功能已迁移到VideoDownloader类，
    此类保留是为了向后兼容，新代码应直接使用VideoDownloader类
    """
    
    def __init__(self, config):
        """
        初始化视频解析器
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 创建VideoDownloader实例
        self.downloader = VideoDownloader(config)
        
    def is_supported_url(self, url: str) -> bool:
        """
        检查URL是否为支持的视频平台
        
        Args:
            url: 视频URL
            
        Returns:
            bool: 是否支持
        """
        try:
            for platform, info in self.config.SUPPORTED_PLATFORMS.items():
                for pattern in info['patterns']:
                    if re.match(pattern, url, re.IGNORECASE):
                        return True
            return False
        except Exception as e:
            self.logger.error(f"URL检查失败: {e}")
            return False
    
    def get_platform_type(self, url: str) -> Optional[str]:
        """
        获取视频平台类型
        
        Args:
            url: 视频URL
            
        Returns:
            Optional[str]: 平台类型
        """
        try:
            for platform, info in self.config.SUPPORTED_PLATFORMS.items():
                for pattern in info['patterns']:
                    if re.match(pattern, url, re.IGNORECASE):
                        return platform
            return None
        except Exception as e:
            self.logger.error(f"平台类型识别失败: {e}")
            return None
    
    def parse_video(self, url: str) -> Dict:
        """
        解析视频信息
        
        Args:
            url: 视频URL
            
        Returns:
            Dict: 视频信息
        """
        try:
            # 使用新的VideoDownloader提取视频信息
            return self.downloader.extract_video_info(url)
        except Exception as e:
            self.logger.error(f"视频解析失败: {e}")
            raise ValueError(str(e))
    
    def _parse_bilibili_info(self, bilibili_info: Dict) -> Dict:
        """
        解析B站API返回的视频信息（保留用于向后兼容）
        
        Args:
            bilibili_info: B站API返回的信息
            
        Returns:
            Dict: 处理后的视频信息
        """
        try:
            pages = bilibili_info.get('pages', [])
            
            if len(pages) == 1:
                # 单个视频
                page = pages[0]
                video_info = {
                    'type': 'single',
                    'platform': 'bilibili',
                    'id': bilibili_info.get('bvid', ''),
                    'title': bilibili_info.get('title', '未知标题'),
                    'description': bilibili_info.get('description', ''),
                    'uploader': bilibili_info.get('uploader', '未知UP主'),
                    'upload_date': str(bilibili_info.get('upload_date', '')),
                    'duration': bilibili_info.get('duration', 0),
                    'view_count': bilibili_info.get('view_count', 0),
                    'like_count': bilibili_info.get('like_count', 0),
                    'webpage_url': bilibili_info.get('webpage_url', ''),
                    'thumbnail': bilibili_info.get('thumbnail', ''),
                    'audio_url': page.get('audio_url', ''),
                    'real_url_source': 'bilibili_api'  # 标记真实链接来源
                }
                
                self.logger.info(f"B站单视频解析成功: {video_info['title']} (真实链接)")
                return video_info
            else:
                # 多P视频
                videos = []
                for page in pages:
                    if page.get('audio_url'):  # 只添加有音频链接的分P
                        video_item = {
                            'part_number': page.get('part_number', 1),
                            'id': f"{bilibili_info.get('bvid', '')}_p{page.get('part_number', 1)}",
                            'title': page.get('title') or f"第{page.get('part_number', 1)}P",
                            'description': '',
                            'duration': page.get('duration', 0),
                            'webpage_url': f"{bilibili_info.get('webpage_url', '')}?p={page.get('part_number', 1)}",
                            'audio_url': page.get('audio_url', ''),
                            'cid': page.get('cid', '')
                        }
                        videos.append(video_item)
                
                if not videos:
                    raise ValueError("没有获取到有效的音频链接")
                
                playlist_info = {
                    'type': 'playlist',
                    'platform': 'bilibili',
                    'id': bilibili_info.get('bvid', ''),
                    'title': bilibili_info.get('title', '未知标题'),
                    'description': bilibili_info.get('description', ''),
                    'uploader': bilibili_info.get('uploader', '未知UP主'),
                    'upload_date': str(bilibili_info.get('upload_date', '')),
                    'webpage_url': bilibili_info.get('webpage_url', ''),
                    'thumbnail': bilibili_info.get('thumbnail', ''),
                    'video_count': len(videos),
                    'total_duration': sum(v.get('duration', 0) for v in videos),
                    'videos': videos,
                    'real_url_source': 'bilibili_api'  # 标记真实链接来源
                }
                
                self.logger.info(f"B站多P视频解析成功: {playlist_info['title']}, 共{len(videos)}个有效分P (真实链接)")
                return playlist_info
                
        except Exception as e:
            self.logger.error(f"B站视频信息解析失败: {e}")
            raise
    
    def _get_best_audio_url(self, info: Dict) -> str:
        """
        获取最佳音频URL（保留用于向后兼容）
        
        Args:
            info: 视频信息
            
        Returns:
            str: 音频URL
        """
        try:
            formats = info.get('formats', [])
            if not formats:
                # 尝试从requested_formats获取
                requested_formats = info.get('requested_formats', [])
                if requested_formats:
                    formats = requested_formats
            
            # 优先选择音频格式
            audio_formats = []
            for fmt in formats:
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    # 纯音频格式
                    audio_formats.append(fmt)
                elif fmt.get('acodec') != 'none':
                    # 包含音频的格式
                    audio_formats.append(fmt)
            
            if audio_formats:
                # 按音频质量排序
                audio_formats.sort(key=lambda x: x.get('abr', 0), reverse=True)
                best_format = audio_formats[0]
                return best_format.get('url', '')
            
            # 如果没有找到音频格式，使用默认URL
            return info.get('url', '')
            
        except Exception as e:
            self.logger.error(f"获取音频URL失败: {e}")
            return info.get('url', '')
    
    def _extract_audio_formats(self, info: Dict) -> List[Dict]:
        """
        提取可用的音频格式信息（保留用于向后兼容）
        
        Args:
            info: 视频信息
            
        Returns:
            List[Dict]: 音频格式列表
        """
        try:
            formats = info.get('formats', [])
            audio_formats = []
            
            for fmt in formats:
                if fmt.get('acodec') != 'none':
                    format_info = {
                        'format_id': fmt.get('format_id', ''),
                        'ext': fmt.get('ext', ''),
                        'acodec': fmt.get('acodec', ''),
                        'abr': fmt.get('abr', 0),
                        'asr': fmt.get('asr', 0),
                        'filesize': fmt.get('filesize', 0),
                        'url': fmt.get('url', '')
                    }
                    audio_formats.append(format_info)
            
            return audio_formats
            
        except Exception as e:
            self.logger.error(f"提取音频格式失败: {e}")
            return []
    
    def _parse_ytdlp_error(self, error_msg: str) -> str:
        """
        解析yt-dlp错误消息（保留用于向后兼容）
        
        Args:
            error_msg: 错误消息
            
        Returns:
            str: 处理后的错误消息
        """
        error_msg_lower = error_msg.lower()
        
        if 'network' in error_msg_lower or 'connection' in error_msg_lower:
            return self.config.ERROR_MESSAGES['network_error']
        elif 'timeout' in error_msg_lower:
            return self.config.ERROR_MESSAGES['timeout_error']
        elif 'not available' in error_msg_lower or 'private' in error_msg_lower:
            return self.config.ERROR_MESSAGES['private_video']
        elif 'geo' in error_msg_lower or 'region' in error_msg_lower:
            return self.config.ERROR_MESSAGES['geo_blocked']
        elif 'age' in error_msg_lower:
            return self.config.ERROR_MESSAGES['age_restricted']
        elif 'rate limit' in error_msg_lower or 'too many' in error_msg_lower:
            return self.config.ERROR_MESSAGES['rate_limit']
        else:
            return self.config.ERROR_MESSAGES['parse_error']
    
    def get_video_info_only(self, url: str) -> Dict:
        """
        仅获取视频基本信息，不提取音频URL（用于快速预览）
        
        Args:
            url: 视频URL
            
        Returns:
            Dict: 视频基本信息
        """
        try:
            # 使用新的VideoDownloader提取视频信息
            info = self.downloader.extract_video_info(url)
            
            # 提取基本信息
            basic_info = {
                'title': info.get('title', '未知标题'),
                'uploader': info.get('uploader', '未知UP主'),
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0),
                'upload_date': info.get('upload_date', ''),
                'platform': info.get('platform', self._get_platform_from_url(url))
            }
            
            return basic_info
                
        except Exception as e:
            self.logger.error(f"获取视频基本信息失败: {e}")
            raise ValueError(str(e))
            
    def _get_platform_from_url(self, url: str) -> str:
        """
        从URL获取平台名称
        
        Args:
            url: 视频URL
            
        Returns:
            str: 平台名称
        """
        return self.downloader._get_platform_from_url(url)