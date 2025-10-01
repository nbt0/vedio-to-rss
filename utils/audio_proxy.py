import os
import hashlib
import requests
import subprocess
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote
from pathlib import Path
import logging
from typing import Optional, Dict, Any
import re
import json

class AudioProxy:
    """
    音频代理服务类
    
    函数级注释：
    - 基于参考项目的DASH检测和转换逻辑
    - 支持B站DASH分片的下载和转换
    - 参考BilibiliDown项目的M4S处理方式
    - 集成SnapAny插件的过滤规则
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.download_dir = Path(config.get('download_dir', 'cache/audio'))
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # 启动清理线程
        if config.get('cleanup_after_hours', 24) > 0:
            self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """启动文件清理线程"""
        def cleanup_worker():
            while True:
                try:
                    self._cleanup_old_files()
                    time.sleep(3600)  # 每小时检查一次
                except Exception as e:
                    self.logger.error(f"清理文件时出错: {e}")
                    time.sleep(3600)
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_old_files(self):
        """清理过期的音频文件"""
        cleanup_hours = self.config.get('cleanup_after_hours', 24)
        cutoff_time = datetime.now() - timedelta(hours=cleanup_hours)
        
        for file_path in self.download_dir.glob('*'):
            if file_path.is_file():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_time:
                    try:
                        file_path.unlink()
                        self.logger.info(f"已清理过期文件: {file_path.name}")
                    except Exception as e:
                        self.logger.error(f"清理文件失败 {file_path}: {e}")
    
    def _get_file_hash(self, url: str) -> str:
        """根据URL生成文件哈希名"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def _is_unusable_bili_url(self, url: str) -> bool:
        """
        检测是否为不可用的B站链接
        
        函数级注释：
        - 基于SnapAny插件的黑名单规则
        - 参考BilibiliDown项目的DASH检测逻辑
        - 过滤掉无法直接播放的链接
        """
        if not url:
            return True
        
        u = str(url).lower()
        
        # SnapAny插件的黑名单规则
        blacklist_patterns = [
            r'.*\.bilivideo\.(com|cn).*/live-bvc/.*m4s',  # 直播DASH分片
            r'.*upos-hz-mirror.*',  # 镜像CDN
            r'.*fnval=4048.*',  # 特定DASH参数
            r'.*fnval=80.*',  # 特定DASH参数
            r'.*dash\?.*',  # DASH查询参数
            r'.*segment_base.*',  # DASH段基础
            r'.*initialization.*',  # DASH初始化段
        ]
        
        for pattern in blacklist_patterns:
            if re.search(pattern, u):
                self.logger.debug(f"检测到不可用链接模式: {pattern}")
                return True
        
        # 检查是否为API JSON响应
        if any(api in u for api in ['api.bilibili.com', 'playurl', 'player/web']):
            try:
                # 尝试获取响应内容检查是否为JSON
                response = requests.head(url, timeout=5)
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    return True
            except Exception:
                pass
        
        return False
    
    def _is_dash_url(self, url: str) -> bool:
        """
        检测是否为DASH分片URL
        
        函数级注释：
        - 参考BilibiliDown项目的DASH检测逻辑
        - 扩展SnapAny插件的过滤规则
        - 识别B站的各种DASH分片格式
        """
        if not url:
            return False
        
        u = str(url).lower()
        
        # 基于参考项目的DASH检测规则
        dash_indicators = [
            '.m4s',  # DASH分片文件扩展名
            'dash',  # DASH协议标识
            'http_dash_segments',  # DASH段标识
            'mcdn.bilivideo.cn',  # B站DASH CDN
            'upos-sz-mirror',  # B站CDN镜像
            'xy123x',  # 特定DASH CDN标识
            'bvc=vod',  # VOD DASH分片
            'live-bvc',  # 直播DASH分片（参考SnapAny黑名单）
            'playurlv3',  # B站API v3 DASH参数
            'segment_base',  # DASH段基础
            'initialization',  # DASH初始化段
        ]
        
        # 检查DASH相关标识
        for indicator in dash_indicators:
            if indicator in u:
                return True
        
        # 检查特定参数组合（参考BilibiliDown项目）
        if ('platform=pc' in u and '.m4s' in u):
            return True
        
        if ('gen=playurlv3' in u and '.m4s' in u):
            return True
        
        # 检查DASH相关的fnval参数
        if any(param in u for param in ['fnval=4048', 'fnval=80', 'fnval=16']):
            return True
        
        return False
    
    def _get_file_extension(self, url: str, content_type: str = None) -> str:
        """
        获取文件扩展名
        
        函数级注释：
        - 基于URL和Content-Type智能判断文件格式
        - 支持DASH分片的正确识别
        """
        # 检查是否为DASH分片
        if self._is_dash_url(url):
            return '.m4s'
        
        # 从URL获取扩展名
        parsed_url = urlparse(url)
        path = parsed_url.path
        if '.' in path:
            ext = os.path.splitext(path)[1].lower()
            if ext in self.config.get('supported_formats', ['.m4s', '.mp3', '.mp4', '.m4a', '.aac', '.flac']):
                return ext
        
        # 从Content-Type获取扩展名
        if content_type:
            content_type = content_type.lower()
            if 'audio/mp4' in content_type or 'audio/m4a' in content_type:
                return '.m4a'
            elif 'video/mp4' in content_type:
                return '.mp4'
            elif 'audio/mpeg' in content_type:
                return '.mp3'
            elif 'audio/aac' in content_type:
                return '.aac'
            elif 'audio/flac' in content_type:
                return '.flac'
            elif 'application/octet-stream' in content_type and '.m4s' in url:
                return '.m4s'
        
        return '.m4s'  # 默认扩展名
    
    def _get_bilibili_headers(self, url: str) -> Dict[str, str]:
        """
        获取B站专用的请求头
        
        函数级注释：
        - 参考BilibiliDown项目的请求头设置
        - 确保DASH分片能够正常下载
        - 模拟真实浏览器环境
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }
        
        # 为B站URL添加Referer和Origin
        if 'bilivideo.com' in url or 'bilibili.com' in url:
            headers['Referer'] = 'https://www.bilibili.com/'
            headers['Origin'] = 'https://www.bilibili.com'
            
            # 为DASH分片添加Range请求头支持
            if self._is_dash_url(url):
                headers['Range'] = 'bytes=0-'
        
        return headers
    
    def _convert_to_mp3(self, input_file: Path, output_file: Path) -> bool:
        """
        使用FFmpeg将音频转换为MP3格式，确保高质量输出
        
        函数级注释：
        - 参考BilibiliDown项目的音频转换逻辑
        - 支持M4S分片到MP3的转换
        - 优化转换参数确保音质和同步
        - 添加详细的错误处理和日志记录
        """
        try:
            ffmpeg_path = self.config.get('ffmpeg_path', 'ffmpeg')
            
            # 增强的音频转换参数，确保高质量和同步
            cmd = [
                ffmpeg_path,
                '-y',                               # 覆盖输出文件
                '-i', str(input_file),              # 输入文件
                '-vn',                              # 不处理视频流
                '-acodec', 'libmp3lame',            # 使用LAME MP3编码器
                '-b:a', '320k',                     # 高质量音频比特率
                '-ar', '44100',                     # 标准采样率
                '-ac', '2',                         # 立体声
                '-af', 'aresample=async=1',         # 音频重采样，确保同步
                '-avoid_negative_ts', 'make_zero',  # 避免负时间戳
                '-fflags', '+genpts',               # 生成时间戳
                '-metadata', 'title=Bilibili Audio', # 添加元数据
                '-metadata', 'encoder=video-to-rss-tool', # 编码器标识
                str(output_file)
            ]
            
            self.logger.info(f"开始音频转换: {input_file.name} -> {output_file.name}")
            
            # 执行FFmpeg命令
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # 检查输出文件质量
                if output_file.exists() and output_file.stat().st_size > 10240:  # 至少10KB
                    self.logger.info(f"音频转换成功: {output_file.name} ({output_file.stat().st_size} bytes)")
                    return True
                else:
                    self.logger.error(f"音频转换失败，输出文件过小或不存在: {output_file}")
                    return False
            else:
                self.logger.error(f"FFmpeg转换失败 (返回码: {result.returncode}): {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("FFmpeg转换超时（超过5分钟）")
            return False
        except FileNotFoundError:
            self.logger.error("FFmpeg未找到，请确保已安装FFmpeg并添加到PATH环境变量")
            return False
        except Exception as e:
            self.logger.error(f"音频转换异常: {e}")
            return False
    
    def _extract_part_number(self, url: str) -> Optional[int]:
        """
        从URL中提取分P编号
        
        函数级注释：
        - 支持多P视频的分片处理
        - 从URL参数中提取part信息
        """
        try:
            # 从URL参数中提取part信息
            if 'part=' in url:
                match = re.search(r'part=(\d+)', url)
                if match:
                    return int(match.group(1))
            
            # 从路径中提取part信息
            if '/part' in url:
                match = re.search(r'/part(\d+)', url)
                if match:
                    return int(match.group(1))
            
            # 从cid参数提取（B站特有）
            if 'cid=' in url:
                match = re.search(r'cid=(\d+)', url)
                if match:
                    return int(match.group(1))
            
            return None
        except Exception:
            return None
    
    def _validate_audio_url(self, url: str) -> bool:
        """
        验证音频URL的有效性
        
        函数级注释：
        - 检查URL是否可访问
        - 验证Content-Type是否为音频格式
        """
        try:
            # 检查是否为不可用链接
            if self._is_unusable_bili_url(url):
                return False
            
            headers = self._get_bilibili_headers(url)
            response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
            
            if response.status_code != 200:
                return False
            
            content_type = response.headers.get('Content-Type', '').lower()
            
            # 检查是否为音频或视频格式
            valid_types = ['audio/', 'video/', 'application/octet-stream']
            if not any(vtype in content_type for vtype in valid_types):
                return False
            
            # 检查Content-Length
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) < 1024:  # 小于1KB可能是错误响应
                return False
            
            return True
        
        except Exception as e:
            self.logger.debug(f"URL验证失败: {e}")
            return False
    
    def get_proxy_url(self, original_url: str, base_url: str = '') -> str:
        """生成代理URL（供RSS与播放页使用）"""
        file_hash = self._get_file_hash(original_url)
        proxy_prefix = self.config.get('proxy_url_prefix', '/audio/')
        return f"{base_url}{proxy_prefix}{file_hash}"

    def get_local_file_url(self, original_url: str, base_url: str = '') -> Optional[str]:
        """获取本地已下载音频文件的可访问URL"""
        try:
            file_hash = self._get_file_hash(original_url)
            # 支持分P后缀的文件匹配
            candidates = list(self.download_dir.glob(f"{file_hash}*.mp3"))
            if not candidates:
                candidates = list(self.download_dir.glob(f"{file_hash}*.m4s"))
            if not candidates:
                candidates = list(self.download_dir.glob(f"{file_hash}*.mp4"))
            if candidates:
                filename = candidates[0].name
                return f"{base_url}/static/audio/{filename}"
            return None
        except Exception as e:
            self.logger.error(f"获取本地文件URL失败: {e}")
            return None

    def process_audio_url(self, url: str, part_number: Optional[int] = None, mode: str = 'proxy', base_url: str = '') -> Optional[str]:
        """
        处理音频URL，支持DASH分片的下载和转换，并返回可访问URL
        
        Args:
            url: 音频URL
            part_number: 分P编号（可选）
            mode: 处理模式（direct/download/proxy）
            base_url: 基础站点URL（用于拼接静态或代理路径）
        
        Returns:
            Optional[str]: 可访问的音频URL或None
        """
        if not url:
            return None
        
        try:
            if mode == 'direct':
                return url
            
            # 先判断是否为DASH分片，DASH分片不做有效性验证直接下载转换
            is_dash = self._is_dash_url(url)
            
            # 提取分P编号
            if part_number is None:
                part_number = self._extract_part_number(url)
            part_suffix = f"_part{part_number}" if part_number else ""
            file_hash = self._get_file_hash(url)
            
            local_file_path: Optional[str] = None
            if is_dash:
                local_file_path = self._download_and_convert_dash(url, file_hash, part_suffix)
            else:
                # 非DASH先验证可用性
                if not self._validate_audio_url(url):
                    self.logger.warning(f"音频URL验证失败: {url}")
                    # 验证失败走代理
                    return self.get_proxy_url(url, base_url)
                local_file_path = self._download_direct_audio(url, file_hash, part_suffix)
            
            if mode == 'download':
                # 返回静态服务可访问的URL
                if local_file_path:
                    filename = Path(local_file_path).name
                    return f"{base_url}/static/audio/{filename}"
                # 下载失败则回退代理
                return self.get_proxy_url(url, base_url)
            else:
                # 代理模式
                from urllib.parse import quote
                safe_chars = ':/?#[]@!$&\'()*+,;='
                encoded_url = quote(url, safe=safe_chars)
                return self.get_proxy_url(url, base_url) + f"?url={encoded_url}"
        
        except Exception as e:
            self.logger.error(f"处理音频URL失败: {e}")
            return None
    
    def _download_and_convert_dash(self, url: str, file_hash: str, part_suffix: str) -> Optional[str]:
        """
        下载DASH分片并转换为MP3
        
        函数级注释：
        - 参考BilibiliDown项目的M4S下载逻辑
        - 使用FFmpeg进行格式转换
        - 增强错误处理和重试机制
        """
        try:
            # 临时文件路径（M4S格式）
            temp_file = self.download_dir / f"{file_hash}{part_suffix}.m4s"
            # 最终文件路径（MP3格式）
            final_file = self.download_dir / f"{file_hash}{part_suffix}.mp3"
            
            # 如果最终文件已存在，直接返回
            if final_file.exists():
                self.logger.info(f"音频文件已存在: {final_file.name}")
                return str(final_file)
            
            # 下载DASH分片
            headers = self._get_bilibili_headers(url)
            
            # 支持重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.get(url, headers=headers, stream=True, timeout=30)
                    response.raise_for_status()
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    self.logger.warning(f"下载重试 {attempt + 1}/{max_retries}: {e}")
                    time.sleep(2)
            
            # 保存临时文件
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            self.logger.info(f"DASH分片下载完成: {temp_file.name}")
            
            # 验证下载的文件大小
            if temp_file.stat().st_size < 1024:
                self.logger.error("下载的文件过小，可能是错误响应")
                temp_file.unlink()
                return None
            
            # 转换为MP3
            if self._convert_to_mp3(temp_file, final_file):
                # 删除临时文件
                try:
                    temp_file.unlink()
                except Exception as e:
                    self.logger.warning(f"删除临时文件失败: {e}")
                
                return str(final_file)
            else:
                # 转换失败，删除临时文件
                try:
                    temp_file.unlink()
                except Exception:
                    pass
                return None
        
        except Exception as e:
            self.logger.error(f"下载和转换DASH分片失败: {e}")
            return None
    
    def _download_direct_audio(self, url: str, file_hash: str, part_suffix: str) -> Optional[str]:
        """
        下载直接音频文件
        
        函数级注释：
        - 处理非DASH的直接音频链接
        - 根据格式决定是否需要转换
        - 增强格式检测和处理
        """
        try:
            # 获取原始文件扩展名
            headers = self._get_bilibili_headers(url)
            
            # 先发送HEAD请求获取Content-Type
            head_response = requests.head(url, headers=headers, timeout=10)
            content_type = head_response.headers.get('Content-Type', '')
            
            original_ext = self._get_file_extension(url, content_type)
            
            # 确定最终文件路径
            if original_ext in ['.mp3']:
                # 已经是MP3，直接下载
                final_file = self.download_dir / f"{file_hash}{part_suffix}.mp3"
                need_convert = False
            else:
                # 需要转换的格式
                temp_file = self.download_dir / f"{file_hash}{part_suffix}{original_ext}"
                final_file = self.download_dir / f"{file_hash}{part_suffix}.mp3"
                need_convert = True
            
            # 如果最终文件已存在，直接返回
            if final_file.exists():
                self.logger.info(f"音频文件已存在: {final_file.name}")
                return str(final_file)
            
            # 下载文件
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            download_path = final_file if not need_convert else temp_file
            
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            self.logger.info(f"音频文件下载完成: {download_path.name}")
            
            # 验证下载的文件大小
            if download_path.stat().st_size < 1024:
                self.logger.error("下载的文件过小，可能是错误响应")
                download_path.unlink()
                return None
            
            # 如果需要转换
            if need_convert:
                if self._convert_to_mp3(temp_file, final_file):
                    # 删除临时文件
                    try:
                        temp_file.unlink()
                    except Exception as e:
                        self.logger.warning(f"删除临时文件失败: {e}")
                    
                    return str(final_file)
                else:
                    # 转换失败，删除临时文件
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass
                    return None
            else:
                return str(final_file)
        
        except Exception as e:
            self.logger.error(f"下载直接音频文件失败: {e}")
            return None
    
    def download_audio(self, url: str, headers: Dict[str, str] = None) -> Optional[str]:
        """
        下载音频文件（兼容性方法）
        
        Args:
            url: 音频URL
            headers: 请求头（可选）
            
        Returns:
            Optional[str]: 音频文件路径或None
        """
        return self.process_audio_url(url)
    
    def get_audio_file_path(self, url: str, part_number: Optional[int] = None) -> Optional[str]:
        """
        获取音频文件路径（如果已存在）
        
        Args:
            url: 音频URL
            part_number: 分P编号（可选）
            
        Returns:
            Optional[str]: 音频文件路径或None
        """
        if not url:
            return None
        
        try:
            file_hash = self._get_file_hash(url)
            part_suffix = f"_part{part_number}" if part_number else ""
            
            # 检查MP3文件是否存在
            mp3_file = self.download_dir / f"{file_hash}{part_suffix}.mp3"
            if mp3_file.exists():
                return str(mp3_file)
            
            return None
        
        except Exception as e:
            self.logger.error(f"获取音频文件路径失败: {e}")
            return None