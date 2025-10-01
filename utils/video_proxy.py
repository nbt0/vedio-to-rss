import os
import hashlib
import requests
import subprocess
import time
from urllib.parse import urlparse
from pathlib import Path
import logging
from typing import Optional, Dict, Any


class VideoProxy:
    """
    视频代理服务类

    目标：当平台只提供 DASH 分片（m4s）或直链无法直接播放时，
    下载视频分片与音频分片并用 FFmpeg 合并为可播放的 MP4，本地提供静态访问。
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self.download_dir = Path(self.config.get('download_dir', 'cache/video'))
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = self.config.get('ffmpeg_path', 'ffmpeg')

    def _get_file_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _is_dash_url(self, url: str) -> bool:
        """
        检测是否为DASH分片URL
        
        增强检测逻辑，支持B站各种DASH格式
        """
        if not url:
            return False
        u = str(url).lower()
        
        # B站DASH分片的关键指标
        dash_indicators = [
            '.m4s',                    # DASH分片文件扩展名
            'dash',                    # DASH协议标识
            'http_dash_segments',      # DASH段标识
            'mcdn.bilivideo.cn',       # B站CDN域名
            'xy123x',                  # B站特殊标识
            'bvc=vod',                 # B站视频点播标识
            'live-bvc',                # B站直播标识
            'playurlv3',               # B站播放URL版本3
            'segment_base',            # DASH段基础
            'initialization',          # DASH初始化段
            'upos-sz-',                # B站存储节点标识
            'upgcxcode'                # B站上传编码标识
        ]
        
        # 检查DASH指标
        has_dash_indicator = any(indicator in u for indicator in dash_indicators)
        
        # 检查B站特殊参数
        dash_params = ['fnval=4048', 'fnval=80', 'fnval=16', 'gen=playurlv3']
        has_dash_param = any(param in u for param in dash_params)
        
        return has_dash_indicator or has_dash_param

    def _is_audio_only_dash(self, url: str) -> bool:
        """
        检测是否为纯音频DASH分片
        
        通过URL特征判断是否为音频轨道
        修复：更准确的音频分片识别逻辑
        """
        if not url or not self._is_dash_url(url):
            return False
            
        u = str(url).lower()
        
        # 音频轨道的特征标识（更全面的检测）
        audio_indicators = [
            # B站音频质量标识
            '-1-30280',     # 320K音频
            '-1-30232',     # 128K音频  
            '-1-30216',     # 64K音频
            '-1-30251',     # 192K音频
            '-1-30250',     # 高质量音频
            # 通用音频参数
            'audio=',       # 音频参数
            'acodec=',      # 音频编解码器
            'quality=audio', # 音频质量标识
            # 音频MIME类型
            'audio%2fmp4',  # URL编码的audio/mp4
            'audio/mp4',    # 音频MP4类型
            'audio%2fm4a',  # URL编码的audio/m4a
            'audio/m4a',    # 音频M4A类型
        ]
        
        # 视频轨道的特征标识（用于排除）
        video_indicators = [
            # B站视频质量标识
            '-1-30112',     # 高清视频
            '-1-30102',     # 超清视频
            '-1-30080',     # 1080P视频
            '-1-30077',     # 720P视频
            '-1-30064',     # 480P视频
            '-1-30032',     # 360P视频
            '-1-30016',     # 240P视频
            # 通用视频参数
            'video=',       # 视频参数
            'vcodec=',      # 视频编解码器
            'quality=video', # 视频质量标识
            # 视频MIME类型
            'video%2fmp4',  # URL编码的video/mp4
            'video/mp4',    # 视频MP4类型
        ]
        
        # 检查是否包含音频标识
        has_audio_indicator = any(indicator in u for indicator in audio_indicators)
        
        # 检查是否包含视频标识（如果有视频标识，则不是纯音频）
        has_video_indicator = any(indicator in u for indicator in video_indicators)
        
        # 记录详细的判断过程
        self.logger.debug(f"DASH分片类型判断: URL={url[:100]}...")
        self.logger.debug(f"包含音频标识: {has_audio_indicator}")
        self.logger.debug(f"包含视频标识: {has_video_indicator}")
        
        # 如果明确包含视频标识，则不是纯音频
        if has_video_indicator:
            self.logger.debug("判断为视频DASH分片（包含视频标识）")
            return False
        
        # 如果包含音频标识且不包含视频标识，则是纯音频
        if has_audio_indicator:
            self.logger.debug("判断为音频DASH分片（包含音频标识且无视频标识）")
            return True
        
        # 默认情况：如果无法明确判断，假设为视频分片（需要音视频合并）
        self.logger.debug("无法明确判断分片类型，默认为视频分片")
        return False

    def _get_bilibili_headers(self, url: str) -> Dict[str, str]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        if 'bilivideo.com' in url or 'bilibili.com' in url:
            headers['Referer'] = 'https://www.bilibili.com/'
            headers['Origin'] = 'https://www.bilibili.com'
        return headers

    def get_local_file_url(self, original_video_url: str, base_url: str = '') -> Optional[str]:
        try:
            file_hash = self._get_file_hash(original_video_url)
            candidates = list(self.download_dir.glob(f"{file_hash}*.mp4"))
            if candidates:
                return f"{base_url}/static/video/{candidates[0].name}"
            return None
        except Exception as e:
            self.logger.error(f"获取本地视频URL失败: {e}")
            return None

    def _download_file(self, url: str, dest: Path) -> bool:
        try:
            headers = self._get_bilibili_headers(url)
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            if dest.exists() and dest.stat().st_size > 1024:
                return True
            self.logger.error(f"下载文件过小或失败: {dest}")
            return False
        except Exception as e:
            self.logger.error(f"下载失败: {e}")
            return False

    def _mux_to_mp4(self, video_path: Path, audio_path: Optional[Path], output_path: Path) -> bool:
        """
        将视频和音频分片合并为MP4文件，确保音视频同步
        
        Args:
            video_path: 视频分片路径
            audio_path: 音频分片路径（可选）
            output_path: 输出MP4文件路径
            
        Returns:
            bool: 合并是否成功
        """
        try:
            if audio_path and audio_path.exists():
                # 有音频轨道时，使用音视频同步参数
                cmd = [
                    self.ffmpeg_path, '-y',
                    '-i', str(video_path),
                    '-i', str(audio_path),
                    '-c:v', 'copy',                    # 复制视频流，不重新编码
                    '-c:a', 'copy',                    # 复制音频流，不重新编码
                    '-async', '1',                     # 音视频同步修正
                    '-vsync', 'cfr',                   # 恒定帧率
                    '-avoid_negative_ts', 'make_zero', # 避免负时间戳
                    '-fflags', '+genpts',              # 生成时间戳
                    '-movflags', '+faststart',         # 优化MP4结构
                    '-map', '0:v:0',                   # 映射第一个视频流
                    '-map', '1:a:0',                   # 映射第一个音频流
                    str(output_path)
                ]
                self.logger.info(f"合并视频和音频分片: {video_path.name} + {audio_path.name}")
            else:
                # 只有视频轨道时，直接封装为 mp4
                cmd = [
                    self.ffmpeg_path, '-y',
                    '-i', str(video_path),
                    '-c:v', 'copy',                    # 复制视频流
                    '-avoid_negative_ts', 'make_zero', # 避免负时间戳
                    '-fflags', '+genpts',              # 生成时间戳
                    '-movflags', '+faststart',         # 优化MP4结构
                    str(output_path)
                ]
                self.logger.info(f"封装视频分片（无音频）: {video_path.name}")
            
            # 执行FFmpeg命令
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            # 检查输出文件
            if output_path.exists() and output_path.stat().st_size > 1024:
                self.logger.info(f"视频合并成功: {output_path.name} ({output_path.stat().st_size} bytes)")
                return True
            else:
                self.logger.error(f"视频合并失败，输出文件过小或不存在: {output_path}")
                return False
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg 合并失败: {e.stderr}")
            return False
        except Exception as e:
            self.logger.error(f"视频合并异常: {e}")
            return False

    def _convert_to_mp4(self, input_path: Path, output_path: Path) -> bool:
        try:
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', str(input_path),
                '-c', 'copy',
                '-movflags', '+faststart',
                str(output_path)
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return output_path.exists() and output_path.stat().st_size > 1024
        except Exception as e:
            self.logger.error(f"FFmpeg 转封装失败: {e}")
            return False

    def process_video_url(self, video_url: str, audio_url: Optional[str] = None, mode: str = 'download', base_url: str = '') -> Optional[str]:
        """
        处理视频URL，返回可访问的URL（优先本地MP4）。
    
        mode: direct/proxy/download（目前实现 direct/download，本地静态MP4）
        
        增强处理逻辑：
        1. 支持纯音频DASH分片转换为MP4（无视频轨道）
        2. 支持视频+音频DASH分片合并
        3. 支持直链视频转封装
        """
        if not video_url:
            return None
    
        try:
            # 直接模式：原样返回
            if mode == 'direct':
                return video_url
    
            file_hash = self._get_file_hash(video_url)
            part_suffix = ''  # 未来可以根据分P补后缀
    
            # 先看是否已有本地文件
            local = self.get_local_file_url(video_url, base_url)
            if local:
                self.logger.info(f"使用已存在的本地文件: {local}")
                return local
    
            # 判断是否为DASH分片
            is_dash = self._is_dash_url(video_url)
            final_mp4 = self.download_dir / f"{file_hash}{part_suffix}.mp4"
            
            self.logger.info(f"开始处理视频URL: {video_url[:100]}...")
            self.logger.info(f"是否为DASH分片: {is_dash}")
            self.logger.info(f"音频URL: {audio_url[:100] if audio_url else 'None'}...")
    
            if is_dash:
                # 检查是否为纯音频DASH分片
                is_audio_only = self._is_audio_only_dash(video_url)
                self.logger.info(f"是否为纯音频DASH分片: {is_audio_only}")
                
                if is_audio_only:
                    # 纯音频DASH分片：下载并转换为MP4容器（音频轨道）
                    temp_audio = self.download_dir / f"{file_hash}{part_suffix}_audio.m4s"
                    
                    self.logger.info(f"下载音频DASH分片到: {temp_audio}")
                    if not self._download_file(video_url, temp_audio):
                        self.logger.error(f"音频DASH分片下载失败: {video_url}")
                        return None
                    
                    # 将音频分片封装为MP4容器
                    self.logger.info(f"转换音频分片为MP4: {temp_audio} -> {final_mp4}")
                    if self._convert_audio_to_mp4(temp_audio, final_mp4):
                        try:
                            temp_audio.unlink()
                        except Exception:
                            pass
                        self.logger.info(f"音频DASH分片转换成功: {final_mp4.name}")
                        return f"{base_url}/static/video/{final_mp4.name}"
                    else:
                        self.logger.error(f"音频DASH分片转换失败: {video_url}")
                        return None
                else:
                    # 视频DASH分片：需要下载视频分片与音频分片并合并
                    temp_video = self.download_dir / f"{file_hash}{part_suffix}_v.m4s"
                    temp_audio = self.download_dir / f"{file_hash}{part_suffix}_a.m4s"
    
                    self.logger.info(f"下载视频DASH分片到: {temp_video}")
                    if not self._download_file(video_url, temp_video):
                        self.logger.error(f"视频DASH分片下载失败: {video_url}")
                        return None
    
                    audio_downloaded = False
                    if audio_url:
                        # 若提供音频URL，则下载
                        self.logger.info(f"下载音频DASH分片到: {temp_audio}")
                        if self._download_file(audio_url, temp_audio):
                            audio_downloaded = True
                            self.logger.info(f"音频分片下载成功: {temp_audio}")
                        else:
                            self.logger.warning("音频分片下载失败，尝试仅封装视频轨道")
                    else:
                        self.logger.info("未提供音频URL，仅封装视频轨道")
    
                    # 合并视频和音频分片
                    audio_path = temp_audio if audio_downloaded else None
                    self.logger.info(f"合并DASH分片: 视频={temp_video}, 音频={audio_path}")
                    
                    if self._mux_to_mp4(temp_video, audio_path, final_mp4):
                        # 清理临时文件
                        try:
                            if temp_video.exists():
                                temp_video.unlink()
                            if audio_path and audio_path.exists():
                                audio_path.unlink()
                        except Exception as e:
                            self.logger.warning(f"清理临时文件失败: {e}")
                        
                        self.logger.info(f"DASH分片合并成功: {final_mp4.name}")
                        return f"{base_url}/static/video/{final_mp4.name}"
                    else:
                        self.logger.error("DASH分片合并失败")
                        return None
            else:
                # 直链：若是 mp4/flv 等，下载后转封装为 mp4
                # 判定扩展名
                path = urlparse(video_url).path
                ext = os.path.splitext(path)[1].lower()
                temp_in = self.download_dir / f"{file_hash}{part_suffix}{ext or '.mp4'}"
    
                self.logger.info(f"下载直链视频: {video_url} -> {temp_in}")
                if not self._download_file(video_url, temp_in):
                    return None
    
                # 若已是 mp4，直接确保 faststart
                if ext == '.mp4':
                    # 直接确保 faststart
                    if self._convert_to_mp4(temp_in, final_mp4):
                        try:
                            temp_in.unlink()
                        except Exception:
                            pass
                        return f"{base_url}/static/video/{final_mp4.name}"
                    return None
                else:
                    if self._convert_to_mp4(temp_in, final_mp4):
                        try:
                            temp_in.unlink()
                        except Exception:
                            pass
                        return f"{base_url}/static/video/{final_mp4.name}"
                    return None
        except Exception as e:
            self.logger.error(f"处理视频URL失败: {e}")
            return None

    def _convert_audio_to_mp4(self, input_path: Path, output_path: Path) -> bool:
        """
        将音频分片转换为MP4容器格式
        
        专门处理纯音频DASH分片（.m4s）转换为MP4容器
        """
        try:
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', str(input_path),
                '-c', 'copy',                    # 复制音频流，不重新编码
                '-movflags', '+faststart',       # 优化MP4结构
                '-f', 'mp4',                     # 强制输出MP4格式
                str(output_path)
            ]
            
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if output_path.exists() and output_path.stat().st_size > 1024:
                self.logger.info(f"音频转MP4成功: {output_path.name}")
                return True
            else:
                self.logger.error(f"音频转MP4失败，输出文件过小: {output_path}")
                return False
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg音频转MP4失败: {e.stderr}")
            return False
        except Exception as e:
            self.logger.error(f"音频转MP4异常: {e}")
            return False