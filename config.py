# -*- coding: utf-8 -*-
"""
视频转RSS工具 - 配置文件

这个文件包含了应用的所有配置选项，包括：
- Flask应用配置
- yt-dlp解析配置
- RSS生成配置
- 日志配置
- 缓存配置
"""

import os
from datetime import timedelta
from utils.exceptions import ConfigError

class Config:
    """基础配置类"""
    
    # Flask应用配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'video-to-rss-secret-key-2024'
    DEBUG = True
    HOST = '0.0.0.0'
    PORT = 5000
    
    # 项目路径配置
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    CACHE_DIR = os.path.join(BASE_DIR, 'cache')
    
    # 确保目录存在
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # 日志配置
    LOG_LEVEL = 'INFO'
    LOG_FILE = os.path.join(LOGS_DIR, 'app.log')
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5
    
    # yt-dlp配置
    YT_DLP_OPTIONS = {
        # 格式选择优先级：
        # 1. 优先选择非DASH的音频格式(m4a/mp3)
        # 2. 其次选择mp4格式的视频
        # 3. 最后选择任何可用格式
        'format': '(bestaudio[ext=m4a]/bestaudio[ext=mp3])/(best[ext=mp4]/best)',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': os.path.join(CACHE_DIR, '%(title)s.%(ext)s'),
        'writeinfojson': False,
        'writesubtitles': False,
        'writeautomaticsub': False,
        'ignoreerrors': True,
        'no_warnings': False,
        'extract_flat': False,
        'quiet': False,
        'verbose': False,
        # 网络配置
        'socket_timeout': 30,
        'retries': 5,  # 增加重试次数
        # User-Agent配置 - 使用最新Chrome版本
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        # HTTP请求头配置
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.bilibili.com/',  # 添加Referer头
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Upgrade-Insecure-Requests': '1'
        },
        # Cookie配置（如果需要）
        'cookiefile': 'bilibili_cookies.txt',
        # 代理配置（如果需要）
        'proxy': None,
    }
    
    # B站特殊配置
    BILIBILI_OPTIONS = {
        'referer': 'https://www.bilibili.com/',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Cache-Control': 'max-age=0'
        }
    }
    
    # RSS配置
    RSS_CONFIG = {
        'title_suffix': ' - 视频转RSS - AI转写专用',
        'description_suffix': '',
        'language': 'zh-CN',
        'copyright': 'Video to RSS Tool',
        'managing_editor': 'admin@localhost',
        'web_master': 'webmaster@localhost',
        'generator': 'Video to RSS Tool v1.0',
        'docs': 'https://www.rssboard.org/rss-specification',
        'ttl': 60,
        'category': 'Technology',
        'audio_url_mode': 'direct'  # 'direct': 直接链接, 'proxy': 代理链接, 'download': 本地下载
    }
    
    # 音频代理配置
    AUDIO_PROXY_CONFIG = {
        'enabled': True,
        'proxy_url_prefix': '/audio/',  # 代理URL前缀
        'download_enabled': True,  # 是否启用本地下载
        'download_dir': os.path.join(CACHE_DIR, 'audio'),  # 音频下载目录
        'max_file_size': 100 * 1024 * 1024,  # 最大文件大小 100MB
        'cleanup_after_hours': 24,  # 24小时后清理下载的文件
        # 支持的音频格式（包含 .m4a 以兼容B站直链音频）
        'supported_formats': ['.m4s', '.m4a', '.mp3', '.mp4', '.flv'],
        'convert_to_mp3': True,  # 是否转换为MP3格式
        'ffmpeg_path': 'ffmpeg'  # FFmpeg路径，如果在PATH中则直接写ffmpeg
    }
    
    # 缓存配置
    CACHE_CONFIG = {
        'enabled': True,
        'expire_time': timedelta(hours=24),  # 缓存24小时
        'max_size': 100,  # 最大缓存条目数
        'cleanup_interval': timedelta(hours=6),  # 清理间隔
    }
    
    # 支持的视频平台
    SUPPORTED_PLATFORMS = {
        'bilibili': {
            'name': 'B站',
            'patterns': [
                r'https?://(?:www\.)?bilibili\.com/video/[Bb][Vv][0-9A-Za-z]+',
                r'https?://(?:www\.)?bilibili\.com/video/av\d+',
                r'https?://b23\.tv/[0-9A-Za-z]+',
            ],
            'extractor': 'BiliBili',
        },
        'youtube': {
            'name': 'YouTube',
            'patterns': [
                r'https?://(?:www\.)?youtube\.com/watch\?v=[0-9A-Za-z_-]+',
                r'https?://youtu\.be/[0-9A-Za-z_-]+',
                r'https?://(?:www\.)?youtube\.com/embed/[0-9A-Za-z_-]+',
            ],
            'extractor': 'Youtube',
        },
        'douyin': {
            'name': '抖音',
            'patterns': [
                r'https?://(?:www\.)?douyin\.com/video/\d+',
                r'https?://v\.douyin\.com/[0-9A-Za-z]+',
            ],
            'extractor': 'Douyin',
        },
    }
    
    # 错误消息配置
    ERROR_MESSAGES = {
        'invalid_url': '无效的视频链接，请检查URL格式',
        'unsupported_platform': '暂不支持该视频平台',
        'network_error': '网络连接失败，请检查网络设置',
        'parse_error': '视频解析失败，可能是视频不存在或已被删除',
        'timeout_error': '解析超时，请稍后重试',
        'server_error': '服务器内部错误，请联系管理员',
        'rate_limit': '请求过于频繁，请稍后重试',
        'geo_blocked': '该视频在当前地区不可用',
        'private_video': '该视频为私有视频，无法访问',
        'age_restricted': '该视频有年龄限制，无法解析',
    }
    
    # 性能配置
    PERFORMANCE_CONFIG = {
        'max_concurrent_downloads': 3,  # 最大并发下载数
        'download_timeout': 300,  # 下载超时时间（秒）
        'max_file_size': 500 * 1024 * 1024,  # 最大文件大小（500MB）
        'cleanup_old_files': True,  # 是否清理旧文件
        'cleanup_age_days': 7,  # 清理多少天前的文件
    }
    
    # 安全配置
    SECURITY_CONFIG = {
        'rate_limit_per_minute': 10,  # 每分钟最大请求数
        'rate_limit_per_hour': 100,  # 每小时最大请求数
        'max_url_length': 2048,  # 最大URL长度
        'allowed_domains': [],  # 允许的域名（空表示允许所有）
        'blocked_domains': [],  # 禁止的域名
    }

class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    YT_DLP_OPTIONS = Config.YT_DLP_OPTIONS.copy()
    YT_DLP_OPTIONS.update({
        'verbose': True,
        'quiet': False,
    })

class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-this-in-production'
    YT_DLP_OPTIONS = Config.YT_DLP_OPTIONS.copy()
    YT_DLP_OPTIONS.update({
        'verbose': False,
        'quiet': True,
    })

class TestingConfig(Config):
    """测试环境配置"""
    TESTING = True
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    CACHE_CONFIG = Config.CACHE_CONFIG.copy()
    CACHE_CONFIG.update({
        'enabled': False,  # 测试时禁用缓存
    })

# 配置映射
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config(config_name=None):
    """获取配置对象"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    return config.get(config_name, config['default'])


def validate_config(config_obj):
    """验证配置的有效性"""
    try:
        # 验证必需的目录
        required_dirs = [config_obj.LOGS_DIR, config_obj.CACHE_DIR]
        for dir_path in required_dirs:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
        
        # 验证日志配置
        if not isinstance(config_obj.LOG_MAX_BYTES, int) or config_obj.LOG_MAX_BYTES <= 0:
            raise ConfigError("LOG_MAX_BYTES must be a positive integer")
        
        if not isinstance(config_obj.LOG_BACKUP_COUNT, int) or config_obj.LOG_BACKUP_COUNT < 0:
            raise ConfigError("LOG_BACKUP_COUNT must be a non-negative integer")
        
        # 验证缓存配置
        if config_obj.CACHE_CONFIG['enabled']:
            if not isinstance(config_obj.CACHE_CONFIG['max_size'], int) or config_obj.CACHE_CONFIG['max_size'] <= 0:
                raise ConfigError("CACHE_CONFIG.max_size must be a positive integer")
        
        # 验证性能配置
        if config_obj.PERFORMANCE_CONFIG['max_concurrent_downloads'] <= 0:
            raise ConfigError("max_concurrent_downloads must be positive")
        
        if config_obj.PERFORMANCE_CONFIG['download_timeout'] <= 0:
            raise ConfigError("download_timeout must be positive")
        
        # 验证安全配置
        if config_obj.SECURITY_CONFIG['rate_limit_per_minute'] <= 0:
            raise ConfigError("rate_limit_per_minute must be positive")
        
        if config_obj.SECURITY_CONFIG['max_url_length'] <= 0:
            raise ConfigError("max_url_length must be positive")
        
        return True
        
    except Exception as e:
        raise ConfigError(f"Configuration validation failed: {str(e)}")


def get_env_var(key, default=None, var_type=str, required=False):
    """
    安全地获取环境变量
    
    Args:
        key: 环境变量名
        default: 默认值
        var_type: 变量类型 (str, int, bool, float)
        required: 是否必需
    
    Returns:
        转换后的环境变量值
    """
    value = os.environ.get(key, default)
    
    if required and value is None:
        raise ConfigError(f"Required environment variable '{key}' is not set")
    
    if value is None:
        return None
    
    try:
        if var_type == bool:
            return str(value).lower() in ('true', '1', 'yes', 'on')
        elif var_type == int:
            return int(value)
        elif var_type == float:
            return float(value)
        else:
            return str(value)
    except (ValueError, TypeError) as e:
        raise ConfigError(f"Invalid type for environment variable '{key}': {str(e)}")


def update_config_from_env(config_obj):
    """从环境变量更新配置"""
    # Flask配置
    config_obj.DEBUG = get_env_var('DEBUG', config_obj.DEBUG, bool)
    config_obj.HOST = get_env_var('HOST', config_obj.HOST)
    config_obj.PORT = get_env_var('PORT', config_obj.PORT, int)
    config_obj.SECRET_KEY = get_env_var('SECRET_KEY', config_obj.SECRET_KEY)
    
    # 日志配置
    config_obj.LOG_LEVEL = get_env_var('LOG_LEVEL', config_obj.LOG_LEVEL)
    config_obj.LOG_MAX_BYTES = get_env_var('LOG_MAX_BYTES', config_obj.LOG_MAX_BYTES, int)
    config_obj.LOG_BACKUP_COUNT = get_env_var('LOG_BACKUP_COUNT', config_obj.LOG_BACKUP_COUNT, int)
    
    # 缓存配置
    cache_enabled = get_env_var('CACHE_ENABLED', config_obj.CACHE_CONFIG['enabled'], bool)
    if cache_enabled is not None:
        config_obj.CACHE_CONFIG['enabled'] = cache_enabled
    
    # 性能配置
    max_concurrent = get_env_var('MAX_CONCURRENT_DOWNLOADS', 
                                config_obj.PERFORMANCE_CONFIG['max_concurrent_downloads'], int)
    if max_concurrent is not None:
        config_obj.PERFORMANCE_CONFIG['max_concurrent_downloads'] = max_concurrent
    
    return config_obj


# 配置管理器类
class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_name=None):
        self.config_name = config_name or os.environ.get('FLASK_ENV', 'default')
        self._config = None
    
    @property
    def config(self):
        """获取配置对象"""
        if self._config is None:
            self._config = get_config(self.config_name)
            self._config = update_config_from_env(self._config)
            validate_config(self._config)
        return self._config
    
    def reload_config(self, config_name=None):
        """重新加载配置"""
        if config_name:
            self.config_name = config_name
        self._config = None
        return self.config
    
    def get_setting(self, key, default=None):
        """获取配置项"""
        try:
            keys = key.split('.')
            value = self.config
            for k in keys:
                if hasattr(value, k):
                    value = getattr(value, k)
                elif isinstance(value, dict) and value is not None and k in value:
                    value = value[k]
                else:
                    return default
            return value
        except Exception:
            return default
    
    def set_setting(self, key, value):
        """设置配置项（仅在内存中）"""
        try:
            keys = key.split('.')
            config_obj = self.config
            
            # 导航到父级对象
            for k in keys[:-1]:
                if hasattr(config_obj, k):
                    config_obj = getattr(config_obj, k)
                elif isinstance(config_obj, dict) and config_obj is not None and k in config_obj:
                    config_obj = config_obj[k]
                else:
                    raise ConfigError(f"Configuration path '{key}' not found")
            
            # 设置最终值
            final_key = keys[-1]
            if hasattr(config_obj, final_key):
                setattr(config_obj, final_key, value)
            elif isinstance(config_obj, dict):
                config_obj[final_key] = value
            else:
                raise ConfigError(f"Cannot set configuration '{key}'")
                
        except Exception as e:
            raise ConfigError(f"Failed to set configuration '{key}': {str(e)}")


# 全局配置管理器实例
config_manager = ConfigManager()