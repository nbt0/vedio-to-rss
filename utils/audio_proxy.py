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

class AudioProxy:
    """音频代理服务类"""
    
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
    
    def _get_file_extension(self, url: str, content_type: str = None) -> str:
        """获取文件扩展名"""
        # 从URL获取扩展名
        parsed_url = urlparse(url)
        path = parsed_url.path
        if '.' in path:
            ext = os.path.splitext(path)[1].lower()
            if ext in self.config.get('supported_formats', ['.m4s', '.mp3', '.mp4']):
                return ext
        
        # 从Content-Type获取扩展名
        if content_type:
            if 'audio/mp4' in content_type or 'video/mp4' in content_type:
                return '.m4s'
            elif 'audio/mpeg' in content_type:
                return '.mp3'
        
        return '.m4s'  # 默认扩展名
    
    def _convert_to_mp3(self, input_file: Path, output_file: Path) -> bool:
        """使用FFmpeg将音频转换为MP3格式"""
        try:
            ffmpeg_path = self.config.get('ffmpeg_path', 'ffmpeg')
            cmd = [
                ffmpeg_path,
                '-i', str(input_file),
                '-vn',  # 不处理视频
                '-acodec', 'mp3',
                '-ab', '128k',  # 音频比特率
                '-ar', '44100',  # 采样率
                '-y',  # 覆盖输出文件
                str(output_file)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                self.logger.info(f"音频转换成功: {input_file.name} -> {output_file.name}")
                return True
            else:
                self.logger.error(f"FFmpeg转换失败: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            self.logger.error("FFmpeg转换超时")
            return False
        except FileNotFoundError:
            self.logger.error("FFmpeg未找到，请确保已安装FFmpeg")
            return False
        except Exception as e:
            self.logger.error(f"音频转换出错: {e}")
            return False
    
    def download_audio(self, url: str, headers: Dict[str, str] = None) -> Optional[str]:
        """下载音频文件到本地"""
        try:
            # 生成文件名
            file_hash = self._get_file_hash(url)
            
            # 先尝试获取文件信息
            response = requests.head(url, headers=headers, timeout=10)
            content_type = response.headers.get('content-type', '')
            file_ext = self._get_file_extension(url, content_type)
            
            original_file = self.download_dir / f"{file_hash}{file_ext}"
            final_file = original_file
            
            # 如果需要转换为MP3
            if self.config.get('convert_to_mp3', True) and file_ext != '.mp3':
                final_file = self.download_dir / f"{file_hash}.mp3"
            
            # 检查文件是否已存在
            if final_file.exists():
                self.logger.info(f"音频文件已存在: {final_file.name}")
                return final_file.name
            
            # 检查文件大小
            content_length = response.headers.get('content-length')
            if content_length:
                file_size = int(content_length)
                max_size = self.config.get('max_file_size', 100 * 1024 * 1024)
                if file_size > max_size:
                    self.logger.error(f"文件太大: {file_size} bytes > {max_size} bytes")
                    return None
            
            # 下载文件
            self.logger.info(f"开始下载音频: {url}")
            # 禁用系统代理避免连接问题
            proxies = {'http': None, 'https': None}
            response = requests.get(url, headers=headers, stream=True, timeout=30, proxies=proxies)
            response.raise_for_status()
            
            with open(original_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            self.logger.info(f"音频下载完成: {original_file.name}")
            
            # 如果需要转换格式
            if self.config.get('convert_to_mp3', True) and file_ext != '.mp3':
                if self._convert_to_mp3(original_file, final_file):
                    # 删除原始文件
                    original_file.unlink()
                    return final_file.name
                else:
                    # 转换失败，返回原始文件
                    return original_file.name
            
            return final_file.name
            
        except requests.RequestException as e:
            self.logger.error(f"下载音频失败: {e}")
            return None
        except Exception as e:
            self.logger.error(f"处理音频文件时出错: {e}")
            return None
    
    def get_proxy_url(self, original_url: str, base_url: str = '') -> str:
        """生成代理URL"""
        file_hash = self._get_file_hash(original_url)
        proxy_prefix = self.config.get('proxy_url_prefix', '/audio/')
        return f"{base_url}{proxy_prefix}{file_hash}"
    
    def get_local_file_url(self, original_url: str, base_url: str = '') -> Optional[str]:
        """获取本地文件URL"""
        file_hash = self._get_file_hash(original_url)
        
        # 检查可能的文件名
        possible_files = [
            f"{file_hash}.mp3",
            f"{file_hash}.m4s",
            f"{file_hash}.mp4"
        ]
        
        for filename in possible_files:
            file_path = self.download_dir / filename
            if file_path.exists():
                return f"{base_url}/static/audio/{filename}"
        
        return None
    
    def process_audio_url(self, original_url: str, mode: str = 'proxy', base_url: str = '', headers: Dict[str, str] = None) -> str:
        """根据模式处理音频URL"""
        if mode == 'direct':
            return original_url
        elif mode == 'download':
            if self.config.get('download_enabled', True):
                filename = self.download_audio(original_url, headers)
                if filename:
                    return f"{base_url}/static/audio/{filename}"
            # 下载失败，回退到代理模式
            return self.get_proxy_url(original_url, base_url)
        else:  # proxy mode
            return self.get_proxy_url(original_url, base_url)