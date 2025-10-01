"""
哔哩哔哩视频下载器

专门处理B站视频的下载逻辑
"""

import os
import re
from typing import Union, Dict, Any

import yt_dlp

from .base import Downloader, DownloadResult, DownloadQuality, QUALITY_MAP
from ..bilibili_api import BilibiliAPI
from ..bilibili_api import bilibili_api

class BilibiliDownloader(Downloader):
    """哔哩哔哩视频下载器"""
    
    def __init__(self, config=None):
        """
        初始化B站下载器
        
        Args:
            config: 配置对象，包含B站相关配置
        """
        super().__init__()
        self.config = config
        
        # B站请求头
        self.headers = {
            'Referer': 'https://www.bilibili.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def download_audio(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast"
    ) -> DownloadResult:
        """
        下载B站视频的音频
        
        Args:
            video_url: B站视频URL
            output_dir: 输出目录
            quality: 音频质量
            
        Returns:
            DownloadResult: 下载结果
        """
        output_dir = self.get_output_dir(output_dir)
        
        # 提取视频ID
        video_id = self._extract_video_id(video_url)
        output_path = os.path.join(output_dir, f"{video_id}.%(ext)s")
        
        # 设置yt-dlp选项
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': QUALITY_MAP[quality],
            }],
            'noplaylist': True,
            'quiet': False,
            'headers': self.headers
        }
        
        # 下载音频
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            
            # 获取下载结果信息
            title = info.get("title", "")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail", "")
            audio_path = os.path.join(output_dir, f"{video_id}.mp3")
            
            return DownloadResult(
                file_path=audio_path,
                title=title,
                duration=duration,
                cover_url=cover_url,
                platform="bilibili",
                video_id=video_id,
                raw_info=info
            )
    
    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "medium"
    ) -> DownloadResult:
        """
        下载B站完整视频
        
        Args:
            video_url: B站视频URL
            output_dir: 输出目录
            quality: 视频质量
            
        Returns:
            DownloadResult: 下载结果
        """
        output_dir = self.get_output_dir(output_dir)
        
        # 提取视频ID
        video_id = self._extract_video_id(video_url)
        video_path = os.path.join(output_dir, f"{video_id}.mp4")
        
        # 检查是否已存在
        if os.path.exists(video_path):
            info = self.extract_info(video_url)
            return DownloadResult(
                file_path=video_path,
                title=info.get("title", ""),
                duration=info.get("duration", 0),
                cover_url=info.get("thumbnail", ""),
                platform="bilibili",
                video_id=video_id,
                raw_info=info
            )
        
        # 设置输出路径
        output_path = os.path.join(output_dir, f"{video_id}.%(ext)s")
        
        # 设置yt-dlp选项
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',
            'headers': self.headers
        }
        
        # 下载视频
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            
            # 获取下载结果信息
            title = info.get("title", "")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail", "")
            
            return DownloadResult(
                file_path=video_path,
                title=title,
                duration=duration,
                cover_url=cover_url,
                platform="bilibili",
                video_id=video_id,
                raw_info=info
            )
    
    def extract_info(self, video_url: str) -> Dict[str, Any]:
        """
        提取B站视频信息
        
        Args:
            video_url: B站视频URL
            
        Returns:
            Dict: 视频信息
        """
        ydl_opts = {
            'noplaylist': True,
            'quiet': True,
            'headers': self.headers
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(video_url, download=False)

    def get_audio_url(self, url: str, force_mp4: bool = False) -> Dict[str, Any]:
        """
        获取B站音频直链（用于回退路径）
        
        Args:
            url: B站视频URL
            force_mp4: 是否强制返回mp4容器（保留参数，暂不使用）
        
        Returns:
            Dict[str, Any]: 包含是否成功、音频URL、标题、时长等信息
        """
        try:
            # 先用yt-dlp提取信息
            info = self.extract_info(url)
            formats = info.get('formats', [])
            title = info.get('title', '未知标题')
            duration = info.get('duration', 0)

            # 选择最佳可用音频格式（优先m4a，过滤不可用DASH）
            def is_unusable_bili(u: str) -> bool:
                if not u:
                    return True
                u = str(u).lower()
                indicators = ['.m4s', 'playurlv3', 'http_dash_segments', 'mcdn.bilivideo.cn',
                              'bvc=vod', 'fnval=4048', 'dash?', 'segment_base', 'initialization']
                if any(ind in u for ind in indicators):
                    return True
                if ('platform=pc' in u and not (u.endswith('.mp4') or u.endswith('.m4a') or u.endswith('.flv'))):
                    return True
                if ('gen=playurlv3' in u and not (u.endswith('.mp4') or u.endswith('.m4a') or u.endswith('.flv'))):
                    return True
                if ('agrr=' in u and '.m4s' in u):
                    return True
                if 'api.bilibili.com' in u and ('playurl' in u or 'player' in u):
                    return True
                return False

            best_audio = None
            candidates = []
            for fmt in formats:
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    url_candidate = fmt.get('url')
                    if url_candidate and not is_unusable_bili(url_candidate):
                        # 优先 m4a
                        ext = (fmt.get('ext') or '').lower()
                        tbr = fmt.get('tbr') or 0
                        candidates.append((ext == 'm4a', tbr, url_candidate))
            if candidates:
                candidates.sort(reverse=True)
                best_audio = candidates[0][2]

            if best_audio:
                return {
                    'success': True,
                    'audio_url': best_audio,
                    'title': title,
                    'duration': duration,
                    'method': 'yt-dlp'
                }

            # yt-dlp未找到合适的直链时，回退到API方案
            video_id = self._extract_video_id(url)
            try:
                pages = bilibili_api.get_video_pages(video_id) if hasattr(bilibili_api, 'get_video_pages') else []
                cid = pages[0].get('cid') if pages else None
                if cid:
                    audio_url = bilibili_api.get_best_audio_url(video_id, cid)
                    if audio_url:
                        return {
                            'success': True,
                            'audio_url': audio_url,
                            'title': title,
                            'duration': duration,
                            'method': 'bilibili_api'
                        }
            except Exception:
                pass

            return {
                'success': False,
                'error': '未找到可用的音频直链',
                'audio_url': None
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'audio_url': None
            }
    
    def _extract_video_id(self, url: str) -> str:
        """
        从URL中提取B站视频ID
        
        Args:
            url: B站视频URL
            
        Returns:
            str: 视频ID
        """
        # 尝试从URL中提取BV号或av号
        bv_match = re.search(r'BV\w+', url)
        if bv_match:
            return bv_match.group(0)
        
        av_match = re.search(r'av(\d+)', url)
        if av_match:
            return f"av{av_match.group(1)}"
        
        # 如果上述方法失败，尝试使用bilibili_api
        if hasattr(bilibili_api, 'get_video_info'):
            try:
                info = bilibili_api.get_video_info(url)
                return info.get('bvid', '') or f"av{info.get('aid', '')}"
            except:
                pass
        
        # 最后尝试使用yt-dlp提取
        try:
            info = self.extract_info(url)
            return info.get('id', '')
        except:
            # 如果所有方法都失败，生成一个基于URL的唯一ID
            import hashlib
            return f"bili_{hashlib.md5(url.encode()).hexdigest()[:10]}"