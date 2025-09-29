# -*- coding: utf-8 -*-
"""
视频解析模块

这个模块负责：
1. 使用yt-dlp解析各种视频平台的URL
2. 提取视频信息（标题、时长、UP主等）
3. 处理B站分P视频的特殊逻辑
4. 获取音频文件的直链URL
"""

import yt_dlp
import re
import logging
from typing import Dict, List, Optional, Union
from urllib.parse import urlparse
from .bilibili_api import bilibili_api

class VideoParser:
    """视频解析器类"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 基础yt-dlp配置
        self.ydl_opts = self.config.YT_DLP_OPTIONS.copy()
        
    def is_supported_url(self, url: str) -> bool:
        """检查URL是否为支持的视频平台"""
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
        """获取视频平台类型"""
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
        """解析视频信息"""
        try:
            # 检查URL是否支持
            if not self.is_supported_url(url):
                raise ValueError(self.config.ERROR_MESSAGES['unsupported_platform'])
            
            platform = self.get_platform_type(url)
            self.logger.info(f"开始解析 {platform} 视频: {url}")
            

            
            # 根据平台调整配置
            ydl_opts = self._get_platform_options(platform)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 提取视频信息
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    raise ValueError(self.config.ERROR_MESSAGES['parse_error'])
                
                # 处理不同类型的视频
                if 'entries' in info:
                    # 播放列表或分P视频
                    return self._parse_playlist(info, platform)
                else:
                    # 单个视频
                    return self._parse_single_video(info, platform)
                    
        except yt_dlp.DownloadError as e:
            self.logger.error(f"yt-dlp下载错误: {e}")
            error_msg = self._parse_ytdlp_error(str(e))
            raise ValueError(error_msg)
        except Exception as e:
            self.logger.error(f"视频解析失败: {e}")
            raise ValueError(str(e))
    
    def _get_platform_options(self, platform: str) -> Dict:
        """根据平台获取特定的yt-dlp配置"""
        opts = self.ydl_opts.copy()
        
        if platform == 'bilibili':
            # B站特殊配置
            bilibili_opts = self.config.BILIBILI_OPTIONS
            opts.update({
                'referer': bilibili_opts['referer'],
                'user_agent': bilibili_opts['user_agent'],
                'http_headers': bilibili_opts['headers'],
            })
        
        return opts
    
    def _parse_bilibili_info(self, bilibili_info: Dict) -> Dict:
        """解析B站API返回的视频信息"""
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
    
    def _parse_single_video(self, info: Dict, platform: str) -> Dict:
        """解析单个视频"""
        try:
            # 获取最佳音频格式
            audio_url = self._get_best_audio_url(info)
            
            video_info = {
                'type': 'single',
                'platform': platform,
                'id': info.get('id', ''),
                'title': info.get('title', '未知标题'),
                'description': info.get('description', ''),
                'uploader': info.get('uploader', '未知UP主'),
                'upload_date': info.get('upload_date', ''),
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'webpage_url': info.get('webpage_url', ''),
                'thumbnail': info.get('thumbnail', ''),
                'audio_url': audio_url,
                'formats': self._extract_audio_formats(info)
            }
            
            self.logger.info(f"单视频解析成功: {video_info['title']}")
            return video_info
            
        except Exception as e:
            self.logger.error(f"单视频解析失败: {e}")
            raise
    
    def _parse_playlist(self, info: Dict, platform: str) -> Dict:
        """解析播放列表或分P视频"""
        try:
            entries = info.get('entries', [])
            if not entries:
                raise ValueError("播放列表为空")
            
            videos = []
            for i, entry in enumerate(entries):
                if entry is None:
                    continue
                    
                try:
                    # 获取音频URL
                    audio_url = self._get_best_audio_url(entry)
                    
                    video_item = {
                        'part_number': i + 1,
                        'id': entry.get('id', ''),
                        'title': entry.get('title', f'第{i+1}P'),
                        'description': entry.get('description', ''),
                        'duration': entry.get('duration', 0),
                        'webpage_url': entry.get('webpage_url', ''),
                        'audio_url': audio_url
                    }
                    
                    videos.append(video_item)
                    
                except Exception as e:
                    self.logger.warning(f"第{i+1}P解析失败: {e}")
                    continue
            
            if not videos:
                raise ValueError("没有成功解析的视频")
            
            playlist_info = {
                'type': 'playlist',
                'platform': platform,
                'id': info.get('id', ''),
                'title': info.get('title', '未知标题'),
                'description': info.get('description', ''),
                'uploader': info.get('uploader', '未知UP主'),
                'upload_date': info.get('upload_date', ''),
                'webpage_url': info.get('webpage_url', ''),
                'thumbnail': info.get('thumbnail', ''),
                'video_count': len(videos),
                'total_duration': sum(v.get('duration', 0) for v in videos),
                'videos': videos
            }
            
            self.logger.info(f"播放列表解析成功: {playlist_info['title']}, 共{len(videos)}个视频")
            return playlist_info
            
        except Exception as e:
            self.logger.error(f"播放列表解析失败: {e}")
            raise
    
    def _get_best_audio_url(self, info: Dict) -> str:
        """获取最佳音频URL"""
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
        """提取可用的音频格式信息"""
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
        """解析yt-dlp错误消息"""
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
        """仅获取视频基本信息，不提取音频URL（用于快速预览）"""
        try:
            if not self.is_supported_url(url):
                raise ValueError(self.config.ERROR_MESSAGES['unsupported_platform'])
            
            platform = self.get_platform_type(url)
            ydl_opts = self._get_platform_options(platform)
            ydl_opts.update({
                'extract_flat': True,  # 快速提取
                'quiet': True
            })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                basic_info = {
                    'title': info.get('title', '未知标题'),
                    'uploader': info.get('uploader', '未知UP主'),
                    'duration': info.get('duration', 0),
                    'view_count': info.get('view_count', 0),
                    'upload_date': info.get('upload_date', ''),
                    'platform': platform
                }
                
                return basic_info
                
        except Exception as e:
            self.logger.error(f"获取视频基本信息失败: {e}")
            raise ValueError(str(e))