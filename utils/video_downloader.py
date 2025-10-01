"""
视频下载器包装模块

作为新旧代码的桥接层，逐步将原有的video_parser.py中的下载功能迁移到新的下载器模块
基于参考项目BiliNote和BilibiliDown的成功经验，优化B站视频解析功能
"""

import logging
import re
from typing import Dict, Any, Optional, List
import yt_dlp

from .downloaders import DownloaderFactory
from config import get_config
from .bilibili_api import bilibili_api

class VideoDownloader:
    """视频下载器包装类"""
    
    def __init__(self, config=None):
        """
        初始化视频下载器
        
        Args:
            config: 配置对象
        """
        self.logger = logging.getLogger(__name__)
        self.logger.debug(f"VideoDownloader初始化，传入config: {config}")
        
        self.config = config or get_config()
        self.logger.debug(f"VideoDownloader使用config: {self.config}")
        self.logger.debug(f"Config类型: {type(self.config)}")
        
        # 检查config的关键属性
        if hasattr(self.config, 'SUPPORTED_PLATFORMS'):
            self.logger.debug(f"Config有SUPPORTED_PLATFORMS属性: {self.config.SUPPORTED_PLATFORMS}")
        else:
            self.logger.warning("Config缺少SUPPORTED_PLATFORMS属性")
        
        # 基于BiliNote项目的yt-dlp配置，优化B站视频解析
        self.yt_dlp_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': True,
            # 参考BiliNote的格式选择策略，优先选择高质量音频
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            # 添加User-Agent和Referer避免403错误
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            },
            # 参考BilibiliDown项目的配置，支持多P视频
            'playlist_items': '1',  # 默认只获取第一个视频
            'noplaylist': False,  # 允许处理播放列表
            # 添加cookie支持（如果有的话）
            'cookiefile': None,  # 可以后续添加cookie文件路径
            # 网络相关配置 - 优化超时设置
            'socket_timeout': 10,  # 减少socket超时时间
            'retries': 2,  # 减少重试次数
            # 输出配置
            'no_color': True,
            'extract_comments': False,
            'writeinfojson': False,
            'writethumbnail': False,
        }
        
        # 视频格式选择配置（优先选择完整MP4格式）
        self.video_format_opts = {
            'format': 'best[ext=mp4][vcodec!=none][acodec!=none]/best[ext=mp4]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4'
        }
    
    def _is_bilibili_url(self, url: str) -> bool:
        """
        检查是否为B站URL
        
        函数级注释：
        - 支持多种B站URL格式检测
        - 包括短链接b23.tv的识别
        - 支持移动端和桌面端URL
        """
        bilibili_patterns = [
            r'bilibili\.com',
            r'b23\.tv',
            r'bili2233\.cn',
            r'm\.bilibili\.com',  # 移动端
            r'space\.bilibili\.com',  # 用户空间
            r'live\.bilibili\.com'  # 直播
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in bilibili_patterns)
    
    def _is_unusable_bili_url(self, url_to_check: str) -> bool:
        """
        判断B站链接是否不可直接访问
        
        函数级注释：
        - 修复过度过滤问题，允许DASH分片通过
        - 只过滤真正不可访问的API调用和无效链接
        - 保留对明确不可用URL的检测
        """
        if not url_to_check:
            return True
        
        u = str(url_to_check).lower()
        
        # 只过滤明确不可访问的API调用和无效链接
        api_indicators = [
            'api.bilibili.com/x/player/playurl',  # API调用，非直接媒体链接
            'api.bilibili.com/pgc/player/web/playurl',  # 番剧API调用
            'interface.bilibili.com',  # 旧版API接口
        ]
        
        # 检查API调用
        for indicator in api_indicators:
            if indicator in u:
                self.logger.debug(f"过滤API调用URL: {url_to_check}")
                return True
        
        # 检查明确的无效标识（但不包括.m4s，因为DASH分片是可以处理的）
        invalid_indicators = [
            'initialization',  # DASH初始化段（通常无法直接播放）
            'segment_base',  # DASH分段基础信息
        ]
        
        for indicator in invalid_indicators:
            if indicator in u:
                self.logger.debug(f"过滤无效URL标识: {url_to_check}")
                return True
        
        # 检查是否为空的或格式错误的URL
        if not u.startswith(('http://', 'https://')):
            self.logger.debug(f"过滤非HTTP URL: {url_to_check}")
            return True
        
        # 允许所有其他URL通过，包括DASH分片(.m4s)
        self.logger.debug(f"允许URL通过: {url_to_check}")
        return False

    def _safe_truncate_description(self, desc) -> str:
        """
        安全地截断描述文本，避免NoneType错误
        """
        if desc is None:
            return ''
        desc_str = str(desc)
        if len(desc_str) > 200:
            return desc_str[:200] + '...'
        return desc_str
    
    def _extract_best_audio_format(self, formats: List[Dict]) -> Optional[str]:
        """
        从格式列表中提取最佳音频格式
        
        函数级注释：
        - 参考BiliNote项目的格式选择策略
        - 优先选择m4a格式的高质量音频
        - 过滤掉不可用的DASH分片
        """
        if not formats:
            return None
        
        # 按质量排序，优先选择高质量音频
        audio_formats = []
        for fmt in formats:
            if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                # 纯音频格式
                url = fmt.get('url', '')
                if not self._is_unusable_bili_url(url):
                    audio_formats.append(fmt)
        
        if not audio_formats:
            # 如果没有纯音频格式，选择包含音频的格式
            for fmt in formats:
                if fmt.get('acodec') != 'none':
                    url = fmt.get('url', '')
                    if not self._is_unusable_bili_url(url):
                        audio_formats.append(fmt)
        
        if not audio_formats:
            return None
        
        # 按质量排序（参考BiliNote的排序逻辑）
        def format_priority(fmt):
            ext = fmt.get('ext', '')
            abr = fmt.get('abr', 0) or 0
            asr = fmt.get('asr', 0) or 0
            
            # 扩展名优先级
            ext_priority = {
                'm4a': 100,
                'mp3': 90,
                'aac': 80,
                'webm': 70,
                'ogg': 60,
                'flv': 50
            }
            
            return (ext_priority.get(ext, 0), abr, asr)
        
        audio_formats.sort(key=format_priority, reverse=True)
        return audio_formats[0].get('url')

    def extract_video_info(self, url: str, fast_mode: bool = True) -> Dict[str, Any]:
        """
        提取视频信息，添加快速模式
        
        Args:
            url: 视频URL
            fast_mode: 是否使用快速模式，只获取播放链接而不获取详细信息
        
        函数级注释：
        - 对B站视频优先使用bilibili_api获取直接MP4链接
        - 快速模式下跳过yt-dlp的重型操作
        - 其他平台使用yt-dlp进行信息提取
        - 失败时回退到原有API方法
        """
        self.logger.debug(f"开始提取视频信息: {url}, fast_mode={fast_mode}")
        
        try:
            if self._is_bilibili_url(url):
                self.logger.info(f"检测到B站视频，使用bilibili_api快速模式: {url}")
                try:
                    from .bilibili_api import bilibili_api
                    
                    # 提取BV号
                    bvid = bilibili_api.parse_video_url(url)
                    self.logger.debug(f"解析出BV号: {bvid}")
                    
                    if bvid:
                        if fast_mode:
                            # 快速模式：只获取基本信息和播放链接
                            self.logger.info("使用快速模式，只获取播放链接")
                            
                            # 获取视频详情（只获取必要信息）
                            detail = bilibili_api.get_video_detail(bvid)
                            self.logger.debug(f"获取到视频详情: {detail is not None}")
                            
                            if detail:
                                # detail本身就是视频信息，不需要再取View字段
                                view_info = detail
                                self.logger.debug(f"获取到view_info: {view_info is not None}")
                                pages = view_info.get('pages', [])
                                if pages:
                                    cid = pages[0].get('cid')
                                    if cid:
                                        # 快速获取视频和音频URL
                                        video_url = bilibili_api.get_best_video_url(bvid, cid)
                                        audio_url = bilibili_api.get_best_audio_url(bvid, cid)
                                        
                                        self.logger.info(f"快速模式成功获取: {view_info.get('title', '未知标题')}")
                                        
                                        return {
                                            'success': True,
                                            'type': 'single',
                                            'title': view_info.get('title', '未知标题'),
                                            'duration': view_info.get('duration', 0),
                                            'uploader': view_info.get('owner', {}).get('name', '未知作者'),
                                            'upload_date': str(view_info.get('pubdate', '')),
                                            'view_count': view_info.get('stat', {}).get('view', 0),
                                            'like_count': view_info.get('stat', {}).get('like', 0),
                                            'description': self._safe_truncate_description(view_info.get('desc')),  # 安全截断描述
                                            'thumbnail': view_info.get('pic', ''),
                                            'formats': [],  # 快速模式不需要formats字段
                                            'webpage_url': url,
                                            'extractor': 'bilibili_api',
                                            'platform': 'bilibili',
                                            'id': bvid,
                                            'playlist_count': 1,
                                            'video_url': video_url,
                                            'audio_url': audio_url,
                                            'fast_mode': True  # 标记为快速模式
                                        }
                                    else:
                                        self.logger.warning("未获取到有效的cid")
                                        raise Exception("未获取到有效的cid")
                                else:
                                    self.logger.warning("未获取到视频分页信息")
                                    raise Exception("未获取到视频分页信息")
                            else:
                                self.logger.warning("未获取到有效的视频详情")
                                raise Exception("未获取到有效的视频详情")
                        else:
                            # 完整模式处理保持不变
                            raise Exception("BV号解析失败但进入了完整模式分支")
                    else:
                        self.logger.warning("未能解析出有效的BV号")
                        raise Exception("未能解析出有效的BV号")
                except Exception as e:
                    self.logger.warning(f"B站API获取失败，回退到yt-dlp: {e}")
                    if not fast_mode:
                        return self._extract_with_ytdlp(url)
                    else:
                        # 快速模式下返回错误信息而不是抛出异常
                        self.logger.error(f"快速模式下B站API获取失败: {e}")
                        return {
                            'success': False,
                            'error': f"快速模式下B站API获取失败: {e}",
                            'type': 'single',
                            'title': '解析失败',
                            'duration': 0,
                            'uploader': '未知',
                            'upload_date': '',
                            'view_count': 0,
                            'like_count': 0,
                            'description': '视频解析失败',
                            'thumbnail': '',
                            'formats': [],
                            'webpage_url': url,
                            'extractor': 'bilibili_api',
                            'platform': 'bilibili',
                            'id': '',
                            'playlist_count': 1,
                            'video_url': None,
                            'audio_url': None,
                            'fast_mode': True
                        }
            else:
                # 非B站视频
                if fast_mode:
                    # 快速模式下，非B站视频也尝试快速获取
                    self.logger.info("非B站视频，快速模式下使用简化yt-dlp配置")
                    return self._extract_with_ytdlp_fast(url)
                else:
                    return self._extract_with_ytdlp(url)
        except Exception as e:
            self.logger.warning(f"视频信息提取失败，尝试回退方法: {e}")
            if not fast_mode:
                return self._fallback_extract(url)
            else:
                # 快速模式下返回错误信息而不是抛出异常
                self.logger.error(f"快速模式下视频信息提取失败: {e}")
                return {
                    'success': False,
                    'error': f"快速模式下视频信息提取失败: {e}",
                    'type': 'single',
                    'title': '解析失败',
                    'duration': 0,
                    'uploader': '未知',
                    'upload_date': '',
                    'view_count': 0,
                    'like_count': 0,
                    'description': '视频解析失败',
                    'thumbnail': '',
                    'formats': [],
                    'webpage_url': url,
                    'extractor': 'unknown',
                    'platform': 'unknown',
                    'id': '',
                    'playlist_count': 1,
                    'video_url': None,
                    'audio_url': None,
                    'fast_mode': True
                }
    
    def _extract_with_ytdlp_fast(self, url: str) -> Dict[str, Any]:
        """
        使用yt-dlp快速提取视频信息
        
        函数级注释：
        - 优化配置，减少不必要的信息提取
        - 缩短超时时间
        - 只获取基本播放信息
        """
        try:
            # 快速模式配置
            fast_opts = self.yt_dlp_opts.copy()
            fast_opts.update({
                'socket_timeout': 5,  # 更短的超时时间
                'retries': 1,  # 只重试一次
                'extract_flat': True,  # 平面提取，减少处理时间
                'skip_download': True,  # 跳过下载
                'no_check_certificate': True,  # 跳过证书检查
            })
            
            with yt_dlp.YoutubeDL(fast_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    raise Exception("无法获取视频信息")
                
                # 处理播放列表（多P视频）
                if 'entries' in info:
                    # 多P视频，返回第一个视频的信息
                    if info['entries']:
                        video_info = info['entries'][0]
                    else:
                        raise Exception("播放列表为空")
                else:
                    video_info = info
                
                return {
                    'success': True,
                    'title': video_info.get('title', '未知标题'),
                    'duration': video_info.get('duration', 0),
                    'uploader': video_info.get('uploader', '未知作者'),
                    'upload_date': video_info.get('upload_date', ''),
                    'view_count': video_info.get('view_count', 0),
                    'like_count': video_info.get('like_count', 0),
                    'description': (video_info.get('description', '')[:200] + '...') if len(video_info.get('description', '')) > 200 else video_info.get('description', ''),
                    'thumbnail': video_info.get('thumbnail', ''),
                    'formats': video_info.get('formats', [])[:5],  # 只保留前5个格式
                    'webpage_url': video_info.get('webpage_url', url),
                    'extractor': video_info.get('extractor', ''),
                    'platform': 'bilibili' if self._is_bilibili_url(url) else (video_info.get('extractor', '') or 'unknown'),
                    'id': video_info.get('id', ''),
                    'playlist_count': len(info.get('entries', [])) if 'entries' in info else 1,
                    'fast_mode': True
                }
        except Exception as e:
            self.logger.error(f"yt-dlp快速提取视频信息失败: {e}")
            raise

    def _fallback_extract(self, url: str) -> Dict[str, Any]:
        """
        回退提取方法
        
        函数级注释：
        - 当yt-dlp失败时使用原有的下载器
        - 确保服务的稳定性
        """
        try:
            downloader = DownloaderFactory.create_downloader_for_url(url, self.config)
            if downloader:
                return downloader.extract_info(url)
            else:
                raise ValueError("无可用的下载器")
        except Exception as e:
            self.logger.error(f"回退提取也失败: {e}")
            # 返回基本信息
            return {
                'id': '',
                'title': '视频信息获取失败',
                'uploader': '',
                'duration': 0,
                'view_count': 0,
                'thumbnail': '',
                'description': '',
                'upload_date': '',
                'formats': [],
                'webpage_url': url,
                'extractor': 'fallback',
                'platform': 'bilibili' if self._is_bilibili_url(url) else 'fallback'
            }
    
    def get_audio_url(self, url: str, force_mp4: bool = False) -> Dict[str, Any]:
        """
        获取音频URL
        
        函数级注释：
        - 优先使用yt-dlp获取高质量音频链接
        - 对B站视频进行特殊处理，过滤DASH分片
        - 确保返回可直接访问的音频链接
        """
        try:
            # 首先尝试使用yt-dlp
            info = self.extract_video_info(url)
            if info.get('success'):
                formats = info.get('formats', [])
                audio_url = self._extract_best_audio_format(formats)
                
                if audio_url and not self._is_unusable_bili_url(audio_url):
                    return {
                        'success': True,
                        'audio_url': audio_url,
                        'title': info.get('title', '未知标题'),
                        'duration': info.get('duration', 0),
                        'method': 'yt-dlp'
                    }
            
            # 回退到原有方法
            self.logger.info("yt-dlp方法未获取到可用音频链接，尝试回退方法")
            return self._fallback_get_audio_url(url, force_mp4)
            
        except Exception as e:
            self.logger.error(f"获取音频URL失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'audio_url': None
            }
    
    def _fallback_get_audio_url(self, url: str, force_mp4: bool = False) -> Dict[str, Any]:
        """
        回退方法获取音频URL
        
        函数级注释：
        - 使用原有的API方法作为备选
        - 保持向后兼容性
        """
        try:
            # 使用原有的下载器工厂
            platform = self._get_platform_from_url(url)
            downloader = DownloaderFactory.get_downloader(platform)
            
            if downloader:
                result = downloader.get_audio_url(url, force_mp4)
                if result.get('success'):
                    return result
            
            # 最后尝试bilibili_api
            if self._is_bilibili_url(url):
                return bilibili_api.get_audio_url(url)
            
            return {
                'success': False,
                'error': '无法获取音频URL',
                'audio_url': None
            }
            
        except Exception as e:
            self.logger.error(f"回退方法获取音频URL失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'audio_url': None
            }

    def get_video_url(self, url: str, quality: str = 'best') -> Optional[str]:
        """
        获取视频URL
        
        函数级注释：
        - 对B站视频优先使用API获取真实直链
        - 其他平台使用yt-dlp获取视频链接
        - 支持质量选择
        """
        try:
            # B站视频特殊处理：使用API获取真实直链
            if self._is_bilibili_url(url):
                try:
                    from .bilibili_api import bilibili_api
                    
                    # 提取BV号
                    bvid = bilibili_api.parse_video_url(url)
                    if bvid:
                        # 获取视频详情
                        detail = bilibili_api.get_video_detail(bvid)
                        if detail:
                            pages = detail.get('pages', [])
                            if pages:
                                cid = pages[0].get('cid')
                                if cid:
                                    # 使用新的get_best_video_url方法，优先获取直接MP4链接
                                    video_url = bilibili_api.get_best_video_url(bvid, cid)
                                    if video_url:
                                        self.logger.info(f"B站API成功获取视频链接: {video_url[:100]}...")
                                        return video_url
                                
                except Exception as e:
                    self.logger.warning(f"B站API获取失败，回退到yt-dlp: {e}")
            
            # 使用yt-dlp作为备用方案
            opts = self.yt_dlp_opts.copy()
            opts.update(self.video_format_opts)
            
            # 尝试获取完整的MP4格式（包含音视频）
            # 如果没有完整格式，则使用合并格式
            opts['format'] = 'best[ext=mp4][vcodec!=none][acodec!=none]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            
            if quality != 'best':
                quality_formats = {
                    'high': 'best[ext=mp4][vcodec!=none][acodec!=none][height<=1080]/bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best[height<=1080]',
                    'medium': 'best[ext=mp4][vcodec!=none][acodec!=none][height<=720]/bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]',
                    'low': 'best[ext=mp4][vcodec!=none][acodec!=none][height<=480]/bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[ext=mp4][height<=480]/best[height<=480]'
                }
                opts['format'] = quality_formats.get(quality, opts['format'])
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if 'entries' in info:
                    # 播放列表，取第一个
                    info = info['entries'][0]
                
                # 获取最佳格式的URL
                if 'url' in info:
                    return info['url']
                elif 'formats' in info:
                    best_format = self._extract_best_video_format(info['formats'])
                    return best_format.get('url') if best_format else None
                
                return None
                
        except Exception as e:
            self.logger.error(f"获取视频URL失败: {e}")
            return None

    def _extract_best_video_format(self, formats: List[Dict], quality: str = 'best') -> Optional[str]:
        """
        从格式列表中提取最佳视频格式
        
        函数级注释：
        - 优先选择完整的MP4格式（包含音视频）
        - 过滤掉DASH分片（.m4s文件）
        - 返回真实可播放的视频直链URL
        """
        if not formats:
            self.logger.debug("没有可用的格式")
            return None
        
        self.logger.info(f"开始筛选视频格式，总共 {len(formats)} 个格式")
        
        # 第一步：优先选择完整的MP4格式（包含音视频）
        complete_video_formats = []
        for fmt in formats:
            url = fmt.get('url', '')
            format_id = fmt.get('format_id', '')
            ext = fmt.get('ext', '')
            height = fmt.get('height', 0)
            vcodec = fmt.get('vcodec', '')
            acodec = fmt.get('acodec', '')
            
            self.logger.debug(f"检查格式: {format_id}, 扩展名: {ext}, 高度: {height}, "
                            f"视频编码: {vcodec}, 音频编码: {acodec}, URL: {url[:100]}...")
            
            # 过滤条件：
            # 1. 必须有视频编码且不为'none'
            # 2. 必须有音频编码且不为'none'（确保包含音频）
            # 3. 扩展名为mp4
            # 4. URL不包含.m4s（过滤DASH分片）
            # 5. URL不包含dash关键词
            if (vcodec and vcodec != 'none' and 
                acodec and acodec != 'none' and 
                ext == 'mp4' and 
                url and '.m4s' not in url.lower() and 
                url and 'dash' not in url.lower() and
                url and 'fragment' not in url.lower()):
                
                complete_video_formats.append(fmt)
                self.logger.info(f"找到完整MP4格式: {format_id}, 音频: {acodec}, 视频: {vcodec}")
        
        # 如果找到完整格式，优先使用
        if complete_video_formats:
            self.logger.info(f"找到 {len(complete_video_formats)} 个完整MP4格式")
            video_formats = complete_video_formats
        else:
            # 如果没有完整格式，退回到只有视频的格式
            self.logger.warning("未找到完整MP4格式，尝试只有视频的格式")
            video_formats = []
            for fmt in formats:
                if (fmt.get('vcodec') != 'none' and 
                    fmt.get('ext') == 'mp4' and 
                    '.m4s' not in fmt.get('url', '').lower()):
                    video_formats.append(fmt)
        
        self.logger.info(f"筛选后可用视频格式数量: {len(video_formats)}")
        
        if not video_formats:
            self.logger.warning("没有找到可用的视频格式")
            return None
        
        # 根据质量过滤
        if quality != 'best':
            height_limits = {
                'high': 1080,
                'medium': 720,
                'low': 480
            }
            height_limit = height_limits.get(quality, 1080)
            filtered_formats = [fmt for fmt in video_formats 
                           if (fmt.get('height') or 0) <= height_limit]
            
            if filtered_formats:
                video_formats = filtered_formats
                self.logger.info(f"按质量 {quality} 过滤后格式数量: {len(video_formats)}")
        
        if not video_formats:
            self.logger.warning(f"按质量 {quality} 过滤后没有可用格式")
            return None
        
        # 按质量排序，优先选择完整格式
        def video_format_priority(fmt):
            ext = fmt.get('ext', '')
            height = fmt.get('height', 0) or 0
            tbr = fmt.get('tbr', 0) or 0
            vbr = fmt.get('vbr', 0) or 0
            acodec = fmt.get('acodec', '')
            vcodec = fmt.get('vcodec', '')
            
            # 完整性优先级（有音频和视频的格式优先）
            completeness_score = 0
            if acodec and acodec != 'none':
                completeness_score += 1000  # 有音频加1000分
            if vcodec and vcodec != 'none':
                completeness_score += 500   # 有视频加500分
            
            # 扩展名优先级
            ext_priority = {
                'mp4': 100,
                'webm': 80,
                'flv': 60,
                'mkv': 40
            }
            
            return (completeness_score, ext_priority.get(ext, 0), height, tbr, vbr)
        
        video_formats.sort(key=video_format_priority, reverse=True)
        
        best_format = video_formats[0]
        best_url = best_format.get('url')
        
        self.logger.info(f"选择最佳视频格式: {best_format.get('format_id')}, "
                        f"扩展名: {best_format.get('ext')}, "
                        f"高度: {best_format.get('height')}, "
                        f"URL: {best_url[:100] if best_url else 'None'}...")
        
        return best_url

    def download_audio(self, url: str, output_dir: Optional[str] = None) -> str:
        """
        下载视频的音频部分
        
        Args:
            url: 视频URL
            output_dir: 输出目录
            
        Returns:
            str: 音频文件路径
        """
        try:
            # 使用下载器工厂创建合适的下载器
            downloader = DownloaderFactory.create_downloader_for_url(url, self.config)
            
            if not downloader:
                self.logger.error(f"不支持的URL: {url}")
                raise ValueError(f"不支持的URL: {url}")
            
            # 下载音频
            result = downloader.download_audio(url, output_dir)
            return result.file_path
            
        except Exception as e:
            self.logger.error(f"下载音频失败: {e}")
            raise
    
    def _get_platform_from_url(self, url: str) -> str:
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