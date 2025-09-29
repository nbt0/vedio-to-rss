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
from utils.bilibili_api import bilibili_api
from utils.audio_proxy import AudioProxy
from config import get_config

# 初始化配置
config = get_config()

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'video-to-rss-secret-key-2024'

# 确保必要目录存在
os.makedirs('logs', exist_ok=True)
os.makedirs('cache', exist_ok=True)
os.makedirs('cache/audio', exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VideoParser:
    """视频解析器类"""
    
    def __init__(self):
        """初始化视频解析器
        
        函数级注释：
        - 优先使用配置文件中的 yt-dlp 选项，以便统一 Cookie、UA 和请求头行为。
        - 初始化时校验 `cookiefile` 是否为 Netscape 格式；若无效则临时移除，避免 yt-dlp 报错。
        - 这样在解析 B 站等站点时，能更好地模拟真实浏览器环境，提高直链获取成功率，同时保证健壮性。
        """
        # 使用配置中的 yt-dlp 选项，确保 Cookie/UA/Headers 一致
        self.ydl_opts = get_config().YT_DLP_OPTIONS.copy()
        # 保留我们对音频的偏好
        self.ydl_opts.update({
            'format': 'bestaudio/best',
            'extractaudio': True,
            'audioformat': 'mp3',
        })

        # 校验 cookiefile 是否有效（Netscape 格式），否则移除避免崩溃
        self._validate_cookiefile()

    def _validate_cookiefile(self):
        """校验并修正 yt-dlp 的 cookiefile 设置
        
        函数级注释：
        - yt-dlp 仅接受 Netscape/Mozilla 格式的 cookies 文件。
        - 若检测为无效格式或无法载入，则从 ydl 选项中移除 `cookiefile`，避免后续解析失败。
        - 用户之后可按指引导出正确格式的 cookies 再启用。
        """
        cf = self.ydl_opts.get('cookiefile')
        if not cf:
            return
        try:
            from http.cookiejar import MozillaCookieJar
            jar = MozillaCookieJar(cf)
            jar.load(ignore_discard=True, ignore_expires=True)
            logger.info(f"cookiefile 校验成功: {cf}")
        except Exception as e:
            logger.warning(f"cookiefile 无效，已临时禁用: {cf}，原因: {e}")
            self.ydl_opts.pop('cookiefile', None)
    
    def extract_video_info(self, url):
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
                        logger.info(f"B站API解析成功，获取到{len(bilibili_info.get('pages'))}个分P")
                        return self._parse_bilibili_info(bilibili_info)
                    else:
                        logger.warning(f"B站API返回数据不完整，回退到yt-dlp")
                except Exception as e:
                    logger.warning(f"B站API获取失败，回退到yt-dlp: {str(e)}")
                    logger.error(f"B站API错误详情: {traceback.format_exc()}")
            
            # 设置yt-dlp的请求头，模拟浏览器访问
            self.ydl_opts['http_headers'] = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com/',
                'Origin': 'https://www.bilibili.com',
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"'
            }
            
            # 添加额外的yt-dlp选项，提高解析成功率
            self.ydl_opts['nocheckcertificate'] = True  # 忽略SSL证书验证
            self.ydl_opts['geo_verification_proxy'] = ''  # 不使用地理位置验证代理
            
            # 检查是否配置了代理
            proxy_config = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')
            if proxy_config:
                logger.info(f"yt-dlp 使用系统代理: {proxy_config}")
                self.ydl_opts['proxy'] = proxy_config
            else:
                # 默认使用本地代理，如果存在的话
                local_proxy = 'http://127.0.0.1:7897'
                try:
                    # 测试代理是否可用
                    test_response = requests.get('https://www.bilibili.com', 
                                               proxies={'http': local_proxy, 'https': local_proxy}, 
                                               timeout=3)
                    if test_response.status_code == 200:
                        logger.info(f"yt-dlp 检测到本地代理可用，使用代理: {local_proxy}")
                        self.ydl_opts['proxy'] = local_proxy
                    else:
                        logger.info("本地代理响应异常，yt-dlp 使用直连模式")
                except Exception as e:
                    logger.info(f"本地代理不可用，yt-dlp 使用直连模式: {e}")
            
            # 对B站视频使用特殊处理
            if 'bilibili.com' in url or 'b23.tv' in url:
                # 增加重试次数和超时时间
                self.ydl_opts['retries'] = 10
                self.ydl_opts['socket_timeout'] = 30
                
                # 使用cookies文件（如果存在且格式正确）
                try:
                    if os.path.exists('bilibili_cookies.txt'):
                        # 检查cookies文件格式是否正确
                        with open('bilibili_cookies.txt', 'r', encoding='utf-8') as f:
                            first_line = f.readline().strip()
                            if first_line.startswith('# Netscape HTTP Cookie File'):
                                self.ydl_opts['cookiefile'] = 'bilibili_cookies.txt'
                                logger.info("使用cookies文件进行B站视频解析")
                            else:
                                logger.warning("cookies文件格式不正确，跳过使用cookies")
                except Exception as cookie_err:
                    logger.warning(f"加载cookies文件失败: {str(cookie_err)}")
                    # 移除cookies配置，确保不会因为cookies问题导致解析失败
                    if 'cookiefile' in self.ydl_opts:
                        del self.ydl_opts['cookiefile']
            
            try:
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    # 增强错误处理，防止JSON解析错误
                    try:
                        info = ydl.extract_info(url, download=False)
                    except json.decoder.JSONDecodeError as json_err:
                        logger.error(f"JSON解析错误: {str(json_err)}")
                        if 'bilibili.com' in url or 'b23.tv' in url:
                            raise Exception(f"B站视频解析失败: 可能是API限制或IP被封禁，建议使用代理或登录账号")
                        else:
                            raise Exception(f"视频解析失败: JSON解析错误，可能是网络问题")
                    except yt_dlp.utils.ExtractorError as extractor_err:
                        logger.error(f"提取器错误: {str(extractor_err)}")
                        if 'bilibili.com' in url or 'b23.tv' in url:
                            raise Exception(f"B站视频解析失败: {str(extractor_err)}，可能需要登录账号或使用代理")
                        else:
                            raise Exception(f"视频解析失败: {str(extractor_err)}")
                    except yt_dlp.utils.DownloadError as dl_err:
                        logger.error(f"下载错误: {str(dl_err)}")
                        if 'bilibili.com' in url or 'b23.tv' in url:
                            raise Exception(f"B站视频解析失败: {str(dl_err)}，可能是视频已失效或需要登录")
                        else:
                            raise Exception(f"视频解析失败: {str(dl_err)}")
                    
                    # 检查info是否为None
                    if info is None:
                        logger.error(f"视频信息提取失败，返回None")
                        raise Exception("视频信息提取失败，可能是网络问题或视频已失效")
                    
                    # 处理B站分P视频
                    if 'entries' in info:
                        # 多P视频处理
                        videos = []
                        for i, entry in enumerate(info['entries']):
                            if entry:
                                videos.append({
                                    'title': entry.get('title', '未知标题'),
                                    'audio_url': self._get_audio_url(entry),  # 修改为audio_url字段
                                    'duration': entry.get('duration', 0),
                                    'description': entry.get('description', ''),
                                    'upload_date': entry.get('upload_date', ''),
                                    'webpage_url': entry.get('webpage_url', url),  # 添加视频页面URL
                                    'part_number': i + 1  # 添加分P编号
                                })
                        return {
                            'type': 'playlist',
                            'title': info.get('title', '视频合集'),
                            'videos': videos,
                            'uploader': info.get('uploader', '未知UP主'),
                            'webpage_url': url  # 添加原始URL
                        }
                    else:
                        # 单个视频处理
                        return {
                            'type': 'single',
                            'title': info.get('title', '未知标题'),
                            'audio_url': self._get_audio_url(info),  # 修改为audio_url字段
                            'duration': info.get('duration', 0),
                            'description': info.get('description', ''),
                            'uploader': info.get('uploader', '未知UP主'),
                            'upload_date': info.get('upload_date', ''),
                            'webpage_url': url  # 添加原始URL
                        }
            except yt_dlp.utils.DownloadError as e:
                logger.error(f"yt-dlp下载错误: {str(e)}")
                if 'bilibili.com' in url or 'b23.tv' in url:
                    logger.error("B站视频解析失败，可能是由于API限制或需要登录")
                    raise Exception(f"B站视频解析失败: {str(e)}")
                else:
                    raise Exception(f"视频解析失败: {str(e)}")
            except Exception as e:
                logger.error(f"视频解析过程中发生错误: {str(e)}")
                logger.error(f"错误详情: {traceback.format_exc()}")
                raise Exception(f"视频解析失败: {str(e)}")
                    
        except Exception as e:
            logger.error(f"视频解析失败: {str(e)}")
            raise Exception(f"视频解析失败: {str(e)}")
    
    def _get_audio_url(self, info):
        """
        从视频信息中提取音频URL
        
        Args:
            info (dict): 视频信息
            
        Returns:
            str: 音频URL
        """
        formats = info.get('formats', [])

        # 优先选择非DASH的 m4a/mp4 直链音频
        # 过滤条件：有音频、无视频、扩展名为 m4a/mp4、协议非 dash
        preferred = [
            f for f in formats
            if f.get('acodec') != 'none'
            and f.get('vcodec') == 'none'
            and (f.get('ext') in ('m4a', 'mp4'))
            and f.get('protocol') not in ('dash', 'http_dash_segments')
        ]
        if preferred:
            # 选择码率更高的音频（abr 或 tbr）
            def rate(x):
                return x.get('abr') or x.get('tbr') or 0
            best = max(preferred, key=rate)
            return best.get('url', '')

        # 次选：包含音视频的 mp4 完整文件（便于直接访问）
        mp4_full = [
            f for f in formats
            if f.get('acodec') != 'none'
            and f.get('vcodec') != 'none'
            and f.get('ext') == 'mp4'
            and f.get('protocol') not in ('dash', 'http_dash_segments')
        ]
        if mp4_full:
            def rate_full(x):
                return x.get('tbr') or 0
            best_full = max(mp4_full, key=rate_full)
            return best_full.get('url', '')

        # 回退：尽量避免返回 DASH 分片的 m4s 链接
        non_dash = [
            f for f in formats
            if f.get('protocol') not in ('dash', 'http_dash_segments')
            and f.get('url')
        ]
        if non_dash:
            return non_dash[0].get('url', '')

        # 最后回退：返回入口 URL
        return info.get('url', '')
    
    def _parse_bilibili_info(self, bilibili_info):
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
             - 若为 DASH 分片（常见为 .m4s 或含 playurlv3 的参数），浏览器直接访问可能报 ERR_INVALID_RESPONSE。
             - 我们将这些视为不可直接访问，触发回退策略用 yt-dlp 重取直链。
             """
             if not url:
                 return True
             u = str(url).lower()
             # 扩展检测条件，确保只返回可直接访问的链接
             return (u.endswith('.m4s')
                     or 'playurlv3' in u
                     or 'http_dash_segments' in u
                     or 'platform=pc' in u and not (u.endswith('.mp4') or u.endswith('.m4a'))
                     or 'gen=playurlv3' in u and not (u.endswith('.mp4') or u.endswith('.m4a')))

         def _fetch_bili_audio_via_ytdlp(page_url: str) -> str:
             """使用yt-dlp为指定B站分P页面获取更可访问的音频直链
             
             函数级注释：
             - 使用与浏览器一致的 Cookie/UA/Headers，提高拿到 m4a/mp4 直链的概率。
             - 仅返回音频直链字符串；发生异常时返回空串以保持鲁棒性。
             """
             try:
                 with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                     info = ydl.extract_info(page_url, download=False)
                     return self._get_audio_url(info) or ''
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
video_parser = VideoParser()

# 初始化音频代理服务
audio_proxy = AudioProxy(config.AUDIO_PROXY_CONFIG)

# 初始化RSS生成器（传入音频代理实例）
from utils.rss_generator import RSSGenerator
rss_generator = RSSGenerator(config, audio_proxy)

@app.route('/')
def index():
    """主页路由"""
    return render_template('index.html')

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
        response = requests.get(original_url, headers=headers, stream=True, timeout=30, proxies=proxies)
        response.raise_for_status()
        
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

@app.route('/parse', methods=['POST'])
def parse_video():
    """
    解析视频API接口
    
    Returns:
        JSON响应
    """
    try:
        data = request.get_json()
        video_url = data.get('url', '').strip()
        
        if not video_url:
            return jsonify({'success': False, 'error': '请输入视频URL'})
        
        # 验证URL格式
        parsed_url = urlparse(video_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return jsonify({'success': False, 'error': 'URL格式不正确'})
        
        logger.info(f"开始解析视频: {video_url}")
        
        # 解析视频信息
        video_info = video_parser.extract_video_info(video_url)
        
        # 生成RSS
        rss_content = rss_generator.generate_rss(video_info, video_url)
        
        logger.info(f"视频解析成功: {video_info.get('title', '未知标题')}")
        
        return jsonify({
            'success': True,
            'video_info': video_info,
            'rss_content': rss_content
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
        video_info = video_parser.extract_video_info(original_url)
        
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
        video_info = video_parser.extract_video_info(video_url)
        
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
    app.run(host='0.0.0.0', port=5000, debug=True)