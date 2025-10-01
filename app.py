#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频转RSS工具 - Flask主应用
功能：将视频URL转换为RSS格式，供AI工具进行音频转写
作者：AI助手
日期：2024
"""

from flask import Flask, render_template, request, jsonify, Response, send_from_directory
import yt_dlp
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
import os
import traceback
from urllib.parse import urlparse
import requests
import re
from utils.bilibili_api import bilibili_api
from utils.audio_proxy import AudioProxy
from utils.video_downloader import VideoDownloader
from utils.video_proxy import VideoProxy
from config import get_config

# 初始化配置
config = get_config()
print(f"DEBUG: 全局config对象: {config}")
print(f"DEBUG: 全局config类型: {type(config)}")
if config:
    print(f"DEBUG: config有SUPPORTED_PLATFORMS: {hasattr(config, 'SUPPORTED_PLATFORMS')}")
else:
    print("DEBUG: config为None!")

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'video-to-rss-default-key-change-in-production')

# 确保必要目录存在
os.makedirs('logs', exist_ok=True)
os.makedirs('cache', exist_ok=True)
os.makedirs('cache/audio', exist_ok=True)
os.makedirs('cache/video', exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,  # 改为DEBUG级别以获取更详细的日志
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 使用新的VideoDownloader类替代原有的VideoParser类
video_downloader = VideoDownloader()

def extract_video_info(url):
    """
    提取视频信息
    
    Args:
        url (str): 视频URL
        
    Returns:
        dict: 视频信息字典
    """
    try:
        # 检查是否为B站视频，优先使用自定义API
        if 'bilibili.com' in url or 'b23.tv' in url:
            try:
                logger.info(f"开始使用B站API解析视频: `{url}`")
                bilibili_info = bilibili_api.get_video_info_with_real_urls(url)
                if bilibili_info and bilibili_info.get('pages'):
                    pages = bilibili_info.get('pages')
                    if pages:
                        logger.info(f"B站API解析成功，获取到{len(pages)}个分P")
                    return _parse_bilibili_info(bilibili_info)
                else:
                    logger.warning(f"B站API返回数据不完整，回退到yt-dlp")
            except Exception as e:
                logger.warning(f"B站API获取失败，回退到yt-dlp: {str(e)}")
                # 增强错误日志记录，但不输出完整堆栈跟踪以避免日志过长
                if "账号未登录" in str(e) or "风控校验失败" in str(e):
                    logger.info(f"B站API访问受限，这是正常现象，将使用yt-dlp作为备用方案")
                else:
                    logger.debug(f"B站API错误详情: {traceback.format_exc()}")
        
        # 使用新的下载器模块提取视频信息
        try:
            video_info = video_downloader.extract_video_info(url)
            return video_info
        except Exception as e:
            logger.error(f"视频信息提取失败: {str(e)}")
            raise
    except Exception as e:
        logger.error(f"视频信息提取失败: {str(e)}")
        raise
    
def _get_audio_url(info):
    """
    从视频信息中提取音频URL
    
    函数级注释：
    - 严格过滤DASH分片链接，确保只返回可播放的MP3/MP4格式
    - 优先选择upos-sz-开头的直链，这些通常是可直接播放的完整文件
    - 使用增强的DASH检测逻辑，避免返回不可播放的.m4s分片
    
    Args:
        info (dict): 视频信息
        
    Returns:
        str: 音频URL
    """
    def _is_dash_segment(url: str) -> bool:
        """检测是否为DASH分片链接"""
        if not url:
            return True
        u = str(url).lower()
        return (u.endswith('.m4s')  # DASH分片扩展名
                or 'playurlv3' in u  # DASH API版本标识
                or 'http_dash_segments' in u  # DASH分片标识
                or 'mcdn.bilivideo.cn' in u  # 标准DASH CDN域名
                or re.search(r'xy\d+x\d+x\d+x\d+xy\.mcdn\.bilivideo\.cn', u)  # 新格式CDN域名
                or 'gen=playurlv3' in u and not (u.endswith('.mp4') or u.endswith('.m4a'))
                or 'dash' in u and '.m4s' in u  # 任何包含dash和m4s的链接
                or 'agrr=' in u and '.m4s' in u  # 带有agrr参数的m4s文件
                or 'bvc=vod' in u and '.m4s' in u  # VOD DASH分片
                or 'cdnid=' in u and '.m4s' in u  # CDN标识的DASH分片
                or 'deadline=' in u and '.m4s' in u  # 带有时效性的DASH分片
                or 'upsig=' in u and '.m4s' in u  # 带有签名的DASH分片
                or '/v1/resource/' in u and '.m4s' in u)  # B站资源服务器的DASH分片

    formats = info.get('formats', [])

    # 优先选择非DASH的 m4a/mp4 直链音频
    # 过滤条件：有音频、无视频、扩展名为 m4a/mp4、协议非 dash、URL不是DASH分片
    preferred = [
        f for f in formats
        if f.get('acodec') != 'none'
        and f.get('vcodec') == 'none'
        and (f.get('ext') in ('m4a', 'mp4'))
        and f.get('protocol') not in ('dash', 'http_dash_segments')
        and not _is_dash_segment(f.get('url', ''))
    ]
    if preferred:
        # 优先选择upos-sz-开头的链接（通常更稳定）
        upos_preferred = [f for f in preferred if f.get('url') and 'upos-sz-' in str(f.get('url', ''))]
        if upos_preferred:
            # 选择码率更高的音频（abr 或 tbr）
            def rate(x):
                return x.get('abr') or x.get('tbr') or 0
            best = max(upos_preferred, key=rate)
            return best.get('url', '')
        
        # 如果没有upos链接，选择其他可用的
        def rate(x):
            return x.get('abr') or x.get('tbr') or 0
        best = max(preferred, key=rate)
        return best.get('url', '')

    # 次选：包含音视频的 mp4 完整文件（便于直接访问）
    # 严格过滤，确保不是DASH分片
    mp4_full = [
        f for f in formats
        if f.get('acodec') != 'none'
        and f.get('vcodec') != 'none'
        and f.get('ext') == 'mp4'
        and f.get('protocol') not in ('dash', 'http_dash_segments')
        and not _is_dash_segment(f.get('url', ''))
        and f.get('url') and 'upos-sz-' in str(f.get('url') or '')  # 优先选择upos存储的完整文件
    ]
    if mp4_full:
        def rate_full(x):
            return x.get('tbr') or 0
        best_full = max(mp4_full, key=rate_full)
        return best_full.get('url', '')

    # 第三选择：任何非DASH的音频格式
    non_dash_audio = [
        f for f in formats
        if f.get('acodec') != 'none'
        and f.get('protocol') not in ('dash', 'http_dash_segments')
        and not _is_dash_segment(f.get('url', ''))
        and f.get('url')
    ]
    if non_dash_audio:
        # 优先选择有upos-sz-前缀的链接（通常更稳定）
        upos_links = [f for f in non_dash_audio if f.get('url') and 'upos-sz-' in str(f.get('url') or '')]
        if upos_links:
            return upos_links[0].get('url', '')
        return non_dash_audio[0].get('url', '')

    # 如果所有格式都是DASH分片，返回空字符串而不是不可播放的链接
    logger.warning("所有可用格式都是DASH分片，无法提供可播放的直链")
    return ''
    
def _parse_bilibili_info(bilibili_info):
    """
    解析B站API返回的信息
    
    Args:
        bilibili_info (dict): B站API返回的信息
        
    Returns:
        dict: 标准化的视频信息
    """
    pages = bilibili_info.get('pages', [])
    
    def _is_unusable_bili_url(url: str) -> bool:
        """判断B站音频链接是否不可直接访问
        
        函数级注释：
        - 检测所有已知的DASH分片特征，包括域名、扩展名、参数等
        - 特别针对B站新的CDN域名格式进行检测
        - 确保只返回真正可播放的MP3/MP4格式链接
        """
        if not url:
            return True
        u = str(url).lower()
        # 扩展检测条件，确保只返回可直接访问的链接
        return (u.endswith('.m4s')  # DASH分片扩展名
                or 'playurlv3' in u  # DASH API版本标识
                or 'http_dash_segments' in u  # DASH分片标识
                or 'mcdn.bilivideo.cn' in u  # 标准DASH CDN域名
                or re.search(r'xy\d+x\d+x\d+x\d+xy\.mcdn\.bilivideo\.cn', u)  # 新格式CDN域名
                or 'platform=pc' in u and not (u.endswith('.mp4') or u.endswith('.m4a'))
                or 'gen=playurlv3' in u and not (u.endswith('.mp4') or u.endswith('.m4a'))
                or 'dash' in u and '.m4s' in u  # 任何包含dash和m4s的链接
                or 'xy123x' in u  # 特定的DASH CDN标识
                or 'agrr=' in u and '.m4s' in u  # 带有agrr参数的m4s文件
                or 'bvc=vod' in u and '.m4s' in u  # VOD DASH分片
                or 'cdnid=' in u and '.m4s' in u  # CDN标识的DASH分片
                or 'deadline=' in u and '.m4s' in u  # 带有时效性的DASH分片
                or 'upsig=' in u and '.m4s' in u  # 带有签名的DASH分片
                or '/v1/resource/' in u and '.m4s' in u)  # B站资源服务器的DASH分片

    def _fetch_bili_audio_via_ytdlp(page_url: str) -> str:
        """使用yt-dlp为指定B站分P页面获取音频直链，即使是DASH分片也返回以供下载转换
        
        函数级注释：
        - 使用与浏览器一致的 Cookie/UA/Headers，提高获取音频链接的概率
        - 即使获取到DASH分片链接，也返回给AudioProxy进行下载和转换
        - 这样可以确保用户能够获得可播放的MP3格式音频
        """
        try:
            logger.info(f"使用yt-dlp获取B站音频链接: {page_url}")
            
            # 使用新的下载器模块获取音频URL
            audio_info = video_downloader.get_audio_url(page_url)
            if audio_info and 'audio_url' in audio_info:
                audio_url = audio_info['audio_url']
                if audio_url:
                    logger.info(f"yt-dlp成功获取音频链接: {audio_url}")
                    return audio_url
                else:
                    logger.warning("yt-dlp获取的音频链接为空")
                    
            # 如果第一次尝试失败，尝试使用不同的参数重新获取
            logger.info("尝试使用不同参数重新获取音频链接...")
            audio_info = video_downloader.get_audio_url(page_url, force_mp4=True)
            if audio_info and 'audio_url' in audio_info:
                audio_url = audio_info['audio_url']
                if audio_url:
                    logger.info(f"yt-dlp强制MP4模式成功获取音频链接: {audio_url}")
                    return audio_url
                    
            return ''
        except Exception as e:
            logger.warning(f"yt-dlp 回退获取直链失败: {e}")
            return ''

    if len(pages) > 1:
        # 多P视频
        videos = []
        for page in pages:
            # 分P页面 URL：主页面 + ?p=分P编号
            part_num = page.get('part_number', 1)
            page_url = f"{bilibili_info.get('webpage_url', '')}?p={part_num}"
            audio_url = page.get('audio_url', '')

            # 若为不可直接访问的 m4s/DASH，回退用 yt-dlp 再取直链
            if _is_unusable_bili_url(audio_url):
                refined = _fetch_bili_audio_via_ytdlp(page_url)
                if refined:
                    audio_url = refined

            # 即使是DASH分片链接，也添加到列表中，让AudioProxy处理下载和转换
            if audio_url:
                videos.append({
                    'title': page.get('title', f"第{part_num}P"),
                    'audio_url': audio_url,
                    'duration': page.get('duration', 0),
                    'description': bilibili_info.get('description', ''),
                    'upload_date': str(bilibili_info.get('upload_date', '')),
                    'webpage_url': page_url,
                    'part_number': part_num
                })
        
        return {
            'type': 'playlist',
            'title': bilibili_info.get('title', '视频合集'),
            'videos': videos,
            'uploader': bilibili_info.get('uploader', '未知UP主'),
            'webpage_url': bilibili_info.get('webpage_url', ''),
            'real_url_source': 'bilibili_api'
        }
    else:
        # 单P视频
        page = pages[0] if pages else {}
        audio_url = page.get('audio_url', '')
        # 单P也做回退（若不可直接访问则用 yt-dlp 重取）
        if _is_unusable_bili_url(audio_url):
            page_url = bilibili_info.get('webpage_url', '')
            refined = _fetch_bili_audio_via_ytdlp(page_url)
            if refined:
                audio_url = refined
        
        # 如果仍然没有音频URL，尝试直接使用yt-dlp获取
        if not audio_url:
            page_url = bilibili_info.get('webpage_url', '')
            refined = _fetch_bili_audio_via_ytdlp(page_url)
            if refined:
                audio_url = refined
        return {
            'type': 'single',
            'title': bilibili_info.get('title', '未知标题'),
            'audio_url': audio_url,
            'duration': bilibili_info.get('duration', 0),
            'description': bilibili_info.get('description', ''),
            'uploader': bilibili_info.get('uploader', '未知UP主'),
            'upload_date': str(bilibili_info.get('upload_date', '')),
            'webpage_url': bilibili_info.get('webpage_url', ''),
            'real_url_source': 'bilibili_api'
        }

# 初始化组件
# 使用video_downloader替代原来的video_parser
# video_parser = VideoParser()  # 已使用video_downloader替代

# 初始化音频代理服务
audio_proxy = AudioProxy(config.AUDIO_PROXY_CONFIG)

# 初始化视频代理服务（使用独立video缓存目录与FFmpeg配置）
video_proxy_config = {
    'download_dir': 'cache/video',
    'ffmpeg_path': config.AUDIO_PROXY_CONFIG.get('ffmpeg_path', 'ffmpeg')
}
video_proxy = VideoProxy(video_proxy_config)

# 初始化RSS生成器（传入音频代理实例）
from utils.rss_generator import RSSGenerator
rss_generator = RSSGenerator(config, audio_proxy)

@app.route('/')
def index():
    """主页路由"""
    return render_template('index.html')

@app.route('/player')
def player_page():
    """简洁播放器页面，支持音频/视频播放并提供下载按钮"""
    try:
        from urllib.parse import unquote
        media_type = (request.args.get('type') or 'audio').strip().lower()
        src = request.args.get('src')
        title = request.args.get('title') or '媒体播放'
        filename = request.args.get('filename') or None

        if not src:
            return jsonify({'error': '缺少媒体资源src参数'}), 400

        # 解码src，确保播放器能正确加载
        src = unquote(src)

        return render_template('player.html', media_type=media_type, src=src, title=title, filename=filename)
    except Exception as e:
        logger.error(f"渲染播放器页面失败: {e}")
        return jsonify({'error': '服务器内部错误'}), 500

@app.route('/config')
def config_page():
    """配置管理页面"""
    return render_template('config.html')

@app.route('/api/config', methods=['GET'])
def get_config_api():
    """获取当前配置"""
    try:
        return jsonify({
            'success': True,
            'audio_url_mode': config.RSS_CONFIG.get('audio_url_mode', 'proxy'),
            'proxy_enabled': config.AUDIO_PROXY_CONFIG.get('enabled', True),
            'download_enabled': config.AUDIO_PROXY_CONFIG.get('download_enabled', True),
            'convert_to_mp3': config.AUDIO_PROXY_CONFIG.get('convert_to_mp3', True)
        })
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置"""
    try:
        data = request.get_json()
        updated = False
        
        if 'audio_url_mode' in data:
            config.RSS_CONFIG['audio_url_mode'] = data['audio_url_mode']
            logger.info(f"配置已更新: audio_url_mode = {data['audio_url_mode']}")
            updated = True
            
        if 'proxy_enabled' in data:
            config.AUDIO_PROXY_CONFIG['enabled'] = data['proxy_enabled']
            logger.info(f"配置已更新: proxy_enabled = {data['proxy_enabled']}")
            updated = True
            
        if 'download_enabled' in data:
            config.AUDIO_PROXY_CONFIG['download_enabled'] = data['download_enabled']
            logger.info(f"配置已更新: download_enabled = {data['download_enabled']}")
            updated = True
            
        if 'convert_to_mp3' in data:
            config.AUDIO_PROXY_CONFIG['convert_to_mp3'] = data['convert_to_mp3']
            logger.info(f"配置已更新: convert_to_mp3 = {data['convert_to_mp3']}")
            updated = True
        
        if updated:
            return jsonify({'success': True, 'message': '配置更新成功'})
        else:
            return jsonify({'success': False, 'message': '缺少必要参数'}), 400
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/audio/<file_hash>')
def proxy_audio(file_hash):
    """音频代理路由"""
    try:
        from urllib.parse import unquote
        
        # 从缓存或数据库中获取原始URL（这里简化处理）
        # 实际应用中应该有一个映射表来存储hash到URL的关系
        original_url = request.args.get('url')
        if not original_url:
            return jsonify({'error': '缺少原始URL参数'}), 400
        
        # URL解码
        original_url = unquote(original_url)
        logger.info(f"代理音频请求: {original_url}")
        
        # 获取B站视频的请求头 - 使用最新Chrome版本标识
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"'
        }
        
        # 代理请求 - 禁用系统代理避免连接问题
        proxies = {'http': None, 'https': None}  # 禁用代理
        try:
            response = requests.get(original_url, headers=headers, stream=True, timeout=30, proxies=proxies)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"音频请求失败: {e}")
            return jsonify({'error': '音频获取失败'}), 502
        
        # 返回音频流
        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        # 构建响应头
        headers = {'Accept-Ranges': 'bytes'}
        
        # 只有当content-length存在时才添加到响应头中
        content_length = response.headers.get('content-length')
        if content_length:
            headers['Content-Length'] = content_length
            
        return Response(generate(), 
                       content_type=response.headers.get('content-type', 'audio/mp4'),
                       headers=headers)
        
    except requests.RequestException as e:
        logger.error(f"音频代理请求失败: {e}")
        return jsonify({'error': '音频获取失败'}), 502
    except Exception as e:
        logger.error(f"音频代理处理失败: {e}")
        return jsonify({'error': '服务器内部错误'}), 500

@app.route('/static/audio/<filename>')
def serve_audio(filename):
    """提供本地音频文件服务"""
    try:
        import os
        audio_dir = config.AUDIO_PROXY_CONFIG.get('download_dir', 'cache/audio')
        
        # 确保目录存在
        if not os.path.exists(audio_dir):
            os.makedirs(audio_dir, exist_ok=True)
        
        # 检查文件是否存在
        file_path = os.path.join(audio_dir, filename)
        if not os.path.exists(file_path):
            logger.warning(f"音频文件不存在: {file_path}")
            return jsonify({'error': '文件不存在'}), 404
        
        logger.info(f"提供音频文件服务: {filename}")
        return send_from_directory(audio_dir, filename)
    except Exception as e:
        logger.error(f"音频文件服务失败: {e}")
        return jsonify({'error': '服务器内部错误'}), 500

# 提供本地视频文件服务
@app.route('/static/video/<filename>')
def serve_video(filename):
    """提供本地视频文件服务"""
    try:
        import os
        video_dir = 'cache/video'
        # 确保目录存在
        if not os.path.exists(video_dir):
            os.makedirs(video_dir, exist_ok=True)
        # 检查文件是否存在
        file_path = os.path.join(video_dir, filename)
        if not os.path.exists(file_path):
            logger.warning(f"视频文件不存在: {file_path}")
            return jsonify({'error': '文件不存在'}), 404
        logger.info(f"提供视频文件服务: {filename}")
        return send_from_directory(video_dir, filename)
    except Exception as e:
        logger.error(f"视频文件服务失败: {e}")
        return jsonify({'error': '服务器内部错误'}), 500

@app.route('/parse', methods=['POST'])
def parse_video():
    """解析视频并生成RSS"""
    try:
        # 获取视频URL
        data = request.get_json()
        logger.debug(f"接收到的数据: {data}")
        video_url = data.get('url', '') if data else ''
        download_type = (data.get('download_type') or 'audio').strip().lower() if data else 'audio'
        
        logger.debug(f"解析后的video_url: {video_url}, 类型: {type(video_url)}")
        logger.debug(f"解析后的download_type: {download_type}, 类型: {type(download_type)}")
        
        if not video_url:
            return jsonify({'success': False, 'error': '请输入视频URL'})
        
        # 记录日志
        logger.info(f"开始解析视频: {video_url or 'None'}")
        
        # 提取视频信息 - 使用快速模式
        logger.debug(f"准备创建VideoDownloader，config: {config}")
        logger.debug(f"config类型: {type(config)}")
        
        try:
            video_downloader = VideoDownloader(config)
            logger.debug("VideoDownloader创建成功")
        except Exception as init_e:
            logger.error(f"VideoDownloader初始化失败: {init_e}")
            logger.error(f"初始化异常详情: {traceback.format_exc()}")
            raise
        
        # 添加异常捕获来定位问题
        try:
            logger.debug(f"开始调用extract_video_info，URL: {video_url or 'None'}")
            video_info = video_downloader.extract_video_info(video_url, fast_mode=True)
            logger.debug(f"extract_video_info返回结果类型: {type(video_info)}")
            logger.debug(f"extract_video_info返回结果: {video_info}")
        except Exception as extract_e:
            logger.error(f"extract_video_info异常: {extract_e}")
            logger.error(f"异常类型: {type(extract_e)}")
            logger.error(f"异常详情: {traceback.format_exc()}")
            return jsonify({'success': False, 'error': f'视频信息提取异常: {extract_e}'})
        
        # 调试：打印video_info的类型和值
        try:
            logger.debug(f"video_info类型: {type(video_info) if video_info is not None else 'None'}")
            if video_info is not None:
                logger.debug(f"video_info值: {video_info}")
            else:
                logger.debug("video_info为None")
        except Exception as debug_e:
            logger.error(f"调试输出失败: {debug_e}")
        
        # 检查video_info是否为None或无效
        if video_info is None:
            logger.error("视频信息提取失败，返回None")
            return jsonify({'success': False, 'error': '视频信息提取失败'})
        
        # 检查是否解析失败
        if not video_info.get('success', True):
            error_msg = video_info.get('error', '视频解析失败')
            logger.error(f"视频解析失败: {error_msg}")
            return jsonify({'success': False, 'error': error_msg})
        
        # 规范化视频类型：如果未提供type，则根据结构自动判定
        if 'type' not in video_info:
            is_playlist = False
            if isinstance(video_info.get('videos'), list) and len(video_info.get('videos')) > 0:
                is_playlist = True
            elif isinstance(video_info.get('entries'), list) and len(video_info.get('entries')) > 0:
                # yt-dlp的playlist结构通常使用entries，这里统一映射为videos
                video_info['videos'] = video_info.get('entries', [])
                is_playlist = True
            video_info['type'] = 'playlist' if is_playlist else 'single'
            logger.info(f"自动设置视频类型为: {video_info['type']}")
        
        # 添加音频URL信息
        if video_info.get('type') == 'single':
            # 单个视频，检查是否已经有video_url和audio_url（来自bilibili_api）
            if video_info.get('extractor') == 'bilibili_api':
                # B站视频已经通过bilibili_api获取了直接链接，无需再次获取
                logger.info(f"B站视频已获取直接链接 - 视频: {video_info.get('video_url', 'None')[:100] if video_info.get('video_url') else 'None'}...")
                logger.info(f"B站视频已获取直接链接 - 音频: {video_info.get('audio_url', 'None')[:100] if video_info.get('audio_url') else 'None'}...")
            else:
                # 非B站视频或B站API失败，使用原有逻辑
                try:
                    video_url_to_use = video_info.get('webpage_url', video_url)
                    # 根据download_type决定补充的链接
                    if download_type == 'video':
                        vinfo = video_downloader.get_video_url(video_url_to_use)
                        video_info['video_url'] = vinfo.get('video_url')
                        # 也尽量补充音频以便前端回退
                        audio_info = video_downloader.get_audio_url(video_url_to_use)
                        video_info['audio_url'] = audio_info.get('audio_url')
                    else:
                        audio_info = video_downloader.get_audio_url(video_url_to_use)
                        video_info['audio_url'] = audio_info.get('audio_url')
                        # 也尝试补充视频直链以便切换
                        vinfo = video_downloader.get_video_url(video_url_to_use)
                        video_info['video_url'] = vinfo.get('video_url')
                    # 确保其他必要字段存在
                    if 'uploader' not in video_info and 'uploader' in audio_info:
                        video_info['uploader'] = audio_info.get('uploader')
                    if 'duration' not in video_info and 'duration' in audio_info:
                        video_info['duration'] = audio_info.get('duration')
                    
                    # 调试日志
                    logger.info(f"获取到音频URL: {video_info.get('audio_url')}")
                except Exception as e:
                    logger.warning(f"获取音频URL失败: {e}")
                    # 确保audio_url字段存在，即使为空
                    video_info['audio_url'] = None
        elif video_info.get('type') == 'playlist' or ('videos' in video_info and isinstance(video_info['videos'], list)):
            # 播放列表，为每个视频添加音频URL
            for video in video_info.get('videos', []):
                video_page_url = video.get('webpage_url') or video.get('url')
                if video_page_url:
                    try:
                        if download_type == 'video':
                            vinfo = video_downloader.get_video_url(video_page_url)
                            video['video_url'] = vinfo.get('video_url')
                            # 同时补音频用于回退
                            audio_info = video_downloader.get_audio_url(video_page_url)
                            video['audio_url'] = audio_info.get('audio_url')
                        else:
                            audio_info = video_downloader.get_audio_url(video_page_url)
                            video['audio_url'] = audio_info.get('audio_url')
                            # 同时补视频用于切换
                            vinfo = video_downloader.get_video_url(video_page_url)
                            video['video_url'] = vinfo.get('video_url')
                        # 调试日志
                        logger.info(f"分P音频/视频: audio={video.get('audio_url')} video={video.get('video_url')}")
                    except Exception as e:
                        logger.warning(f"获取分P音频URL失败: {e}")
                        # 确保audio_url字段存在，即使为空
                        video['audio_url'] = None
                        video['video_url'] = None
        
        # 生成可分享播放页URL（音频MP3、视频MP4）
        base_url = f"http://{config.HOST}:{config.PORT}"
        safe_chars = ':/?#[]@!$&\'()*+,;='
        from urllib.parse import quote

        audio_player_url = None
        video_player_url = None

        # 检查是否为快速模式，快速模式下跳过下载处理，直接返回链接
        is_fast_mode = video_info.get('fast_mode', False)
        
        try:
            if video_info.get('type') == 'single':
                title_for_page = video_info.get('title', '媒体播放')
                aurl = video_info.get('audio_url')
                if aurl:
                    if is_fast_mode:
                        # 快速模式：直接使用原始链接，不进行下载处理
                        audio_player_url = (
                            f"{base_url}/player?type=audio&src={quote(aurl, safe=safe_chars)}"
                            f"&title={quote(title_for_page)}&filename={quote((video_info.get('id') or 'audio') + '.mp3')}"
                        )
                        logger.info("快速模式：直接使用音频原始链接")
                    else:
                        processed_aurl = audio_proxy.process_audio_url(aurl, mode='download', base_url=base_url)
                        if processed_aurl:  # 只有成功处理后才生成播放器链接
                            audio_player_url = (
                                f"{base_url}/player?type=audio&src={quote(processed_aurl, safe=safe_chars)}"
                                f"&title={quote(title_for_page)}&filename={quote((video_info.get('id') or 'audio') + '.mp3')}"
                            )
                        else:
                            logger.warning(f"音频URL处理失败，无法生成播放器链接: {aurl}")
                else:
                    logger.warning("未获取到音频URL，无法生成播放器链接")
                vurl = video_info.get('video_url')
                if vurl:
                    if is_fast_mode:
                        # 快速模式：直接使用原始链接，不进行下载处理
                        video_player_url = (
                            f"{base_url}/player?type=video&src={quote(vurl, safe=safe_chars)}"
                            f"&title={quote(title_for_page)}&filename={quote((video_info.get('id') or 'video') + '.mp4')}"
                        )
                        logger.info("快速模式：直接使用视频原始链接")
                    else:
                        processed_vurl = video_proxy.process_video_url(
                            vurl,
                            audio_url=video_info.get('audio_url'),
                            mode='download',
                            base_url=base_url
                        )
                        if processed_vurl:
                            video_player_url = (
                                f"{base_url}/player?type=video&src={quote(processed_vurl, safe=safe_chars)}"
                                f"&title={quote(title_for_page)}&filename={quote((video_info.get('id') or 'video') + '.mp4')}"
                            )
            else:
                if video_info.get('videos'):
                    first = video_info['videos'][0]
                    title_for_page = first.get('title') or video_info.get('title', '媒体播放')
                    aurl = first.get('audio_url')
                    if aurl:
                        if is_fast_mode:
                            # 快速模式：直接使用原始链接
                            audio_player_url = (
                                f"{base_url}/player?type=audio&src={quote(aurl, safe=safe_chars)}"
                                f"&title={quote(title_for_page)}&filename={quote((first.get('id') or 'audio') + '.mp3')}"
                            )
                            logger.info("快速模式：直接使用音频原始链接")
                        else:
                            processed_aurl = audio_proxy.process_audio_url(aurl, mode='download', base_url=base_url)
                            if processed_aurl:  # 只有成功处理后才生成播放器URL
                                audio_player_url = (
                                    f"{base_url}/player?type=audio&src={quote(processed_aurl, safe=safe_chars)}"
                                    f"&title={quote(title_for_page)}&filename={quote((first.get('id') or 'audio') + '.mp3')}"
                                )
                            else:
                                logger.warning(f"音频URL处理失败，无法生成播放器链接: {aurl}")
                    else:
                        logger.warning("未获取到音频URL，无法生成播放器链接")
                    vurl = first.get('video_url')
                    if vurl:
                        if is_fast_mode:
                            # 快速模式：直接使用原始链接
                            video_player_url = (
                                f"{base_url}/player?type=video&src={quote(vurl, safe=safe_chars)}"
                                f"&title={quote(title_for_page)}&filename={quote((first.get('id') or 'video') + '.mp4')}"
                            )
                            logger.info("快速模式：直接使用视频原始链接")
                        else:
                            processed_vurl = video_proxy.process_video_url(
                                vurl,
                                audio_url=first.get('audio_url'),
                                mode='download',
                                base_url=base_url
                            )
                            if processed_vurl:
                                video_player_url = (
                                    f"{base_url}/player?type=video&src={quote(processed_vurl, safe=safe_chars)}"
                                    f"&title={quote(title_for_page)}&filename={quote((first.get('id') or 'video') + '.mp4')}"
                                )
        except Exception as e:
            logger.warning(f"生成播放页URL失败: {e}")

        # 生成RSS
        rss_content = rss_generator.generate_rss(video_info, video_url)
        
        logger.info(f"视频解析成功: {video_info.get('title', '未知标题')}")
        
        return jsonify({
            'success': True,
            'video_info': video_info,
            'rss_content': rss_content,
            'download_type': download_type,
            'audio_player_url': audio_player_url,
            'video_player_url': video_player_url
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"解析失败: {error_msg}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': error_msg})

@app.route('/audio/<path:encoded_url>')
def get_audio(encoded_url):
    """
    音频代理接口 - 为AI工具提供真实的音频URL
    
    Args:
        encoded_url (str): 编码后的视频URL
        
    Returns:
        音频流响应或重定向到音频URL
    """
    try:
        import base64
        import requests
        from flask import redirect, stream_with_context
        
        # 解码URL
        video_url = base64.b64decode(encoded_url.encode()).decode('utf-8')
        
        logger.info(f"音频请求: {video_url}")
        
        # 检查是否为分P视频请求
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(video_url)
        query_params = parse_qs(parsed_url.query)
        part_number = query_params.get('p', [None])[0]
        
        # 获取原始URL（去除p参数）
        original_url = video_url.split('?p=')[0] if '?p=' in video_url else video_url
        
        # 解析视频获取音频URL
        video_info = video_downloader.extract_video_info(original_url)
        
        audio_url = None
        if video_info['type'] == 'single':
            audio_url = video_info.get('url')
        else:
            # 对于播放列表，根据part_number查找对应视频
            if video_info.get('videos'):
                if part_number:
                    # 查找指定分P
                    for video in video_info['videos']:
                        if str(video.get('part_number')) == str(part_number):
                            audio_url = video.get('url')
                            break
                else:
                    # 默认返回第一个视频
                    audio_url = video_info['videos'][0].get('url')
        
        if not audio_url:
            raise Exception("无法获取音频URL")
        
        logger.info(f"重定向到音频URL: {audio_url}")
        
        # 直接重定向到音频URL
        return redirect(audio_url)
        
    except Exception as e:
        logger.error(f"音频获取失败: {str(e)}")
        return f"音频获取失败: {str(e)}", 404

@app.route('/get_audio')
def get_audio_file():
    """
    获取代理处理后的音频文件
    
    Args:
        file: 音频文件路径（通过query参数传递）
        
    Returns:
        音频文件流响应
    """
    try:
        file_path = request.args.get('file')
        if not file_path:
            return "缺少文件路径参数", 400
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return "音频文件不存在", 404
        
        # 检查文件是否在允许的目录内（安全检查）
        cache_dir = os.path.abspath('cache/audio')
        abs_file_path = os.path.abspath(file_path)
        if not abs_file_path.startswith(cache_dir):
            return "文件路径不合法", 403
        
        logger.info(f"提供音频文件: {file_path}")
        
        # 返回音频文件
        return send_from_directory(
            os.path.dirname(abs_file_path),
            os.path.basename(abs_file_path),
            mimetype='audio/mpeg',
            as_attachment=False
        )
        
    except Exception as e:
        logger.error(f"获取音频文件失败: {str(e)}")
        return f"获取音频文件失败: {str(e)}", 500

@app.route('/rss/<path:encoded_url>')
def get_rss(encoded_url):
    """
    获取RSS内容的直链接口
    
    Args:
        encoded_url (str): 编码后的视频URL
        
    Returns:
        RSS XML响应
    """
    try:
        import base64
        import urllib.parse
        
        # 解码URL
        video_url = base64.b64decode(encoded_url.encode()).decode('utf-8')
        
        logger.info(f"RSS请求: {video_url}")
        
        # 解析视频
        video_info = video_downloader.extract_video_info(video_url)
        
        # 生成RSS
        rss_content = rss_generator.generate_rss(video_info, video_url)
        
        return Response(rss_content, mimetype='application/xml')
        
    except Exception as e:
        logger.error(f"RSS生成失败: {str(e)}")
        error_rss = '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>错误</title>
    <description>RSS生成失败</description>
    <item>
      <title>解析错误</title>
      <description>{}</description>
    </item>
  </channel>
</rss>'''.format(str(e))
        return Response(error_rss, mimetype='application/xml')

if __name__ == '__main__':
    # 确保日志目录存在
    os.makedirs('logs', exist_ok=True)
    
    logger.info("视频转RSS工具启动")
    logger.info("访问地址: http://localhost:5000")
    
    # 启动Flask应用
    # 绑定到0.0.0.0允许外部访问，但用户应使用localhost或实际IP访问
    app.run(host='0.0.0.0', port=5000, debug=False)