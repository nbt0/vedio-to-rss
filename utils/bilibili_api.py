# -*- coding: utf-8 -*-
"""
B站API模块

基于BilibiliDown项目的Java实现，用Python重写B站视频真实链接获取功能
包含WBI加密、视频详情获取、播放链接获取等核心功能
"""

import os
import requests
from http.cookiejar import MozillaCookieJar
import json
import time
import hashlib
import urllib.parse
from typing import Dict, List, Optional, Tuple
import logging
import re
class BilibiliAPI:
    """B站API类，用于获取视频真实链接"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        self.session.trust_env = False
        
        # 检查是否配置了代理
        proxy_config = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')
        if proxy_config:
            self.logger.info(f"使用系统代理: {proxy_config}")
            self.session.proxies = {
                'http': proxy_config,
                'https': proxy_config
            }
        else:
            # 默认使用本地代理，如果存在的话
            local_proxy = 'http://127.0.0.1:7897'
            try:
                # 测试代理是否可用
                test_response = requests.get('https://www.bilibili.com', 
                                           proxies={'http': local_proxy, 'https': local_proxy}, 
                                           timeout=3)
                if test_response.status_code == 200:
                    self.logger.info(f"检测到本地代理可用，使用代理: {local_proxy}")
                    self.session.proxies = {'http': local_proxy, 'https': local_proxy}
                else:
                    self.logger.info("本地代理响应异常，使用直连模式")
                    self.session.proxies = {'http': None, 'https': None}
            except Exception as e:
                self.logger.info(f"本地代理不可用，使用直连模式: {e}")
                self.session.proxies = {'http': None, 'https': None}
        
        self.wbi_img = None
        self.wbi_sub = None
        
        # WBI混淆数组（来自BilibiliDown项目）
        self.mixin_array = [
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42,
            19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54,
            21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
        ]
        
        # 设置请求头 - 使用最新Chrome版本标识
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"'
        })

        # 尝试加载本地 Netscape 格式 Cookie，提升通过风控的成功率
        try:
            cookie_file = 'bilibili_cookies.txt'
            jar = MozillaCookieJar(cookie_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            for c in jar:
                # 将 Cookie 注入到 session，保留域与路径信息
                self.session.cookies.set(c.name, c.value, domain=c.domain, path=c.path)
            self.logger.info(f"已加载 Cookie 文件: {cookie_file}")
        except Exception as e:
            # 未找到或格式不正确则忽略，继续匿名请求
            self.logger.warning(f"Cookie 未加载或无效，将以匿名模式访问。原因: {e}")
    
    def _get_wbi_keys(self) -> Tuple[str, str]:
        """获取WBI加密所需的img_key和sub_key"""
        try:
            if self.wbi_img and self.wbi_sub:
                return self.wbi_img, self.wbi_sub
                
            url = 'https://api.bilibili.com/x/web-interface/nav'
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            if data['code'] != 0:
                raise Exception(f"获取WBI密钥失败: {data['message']}")
            
            wbi_img_url = data['data']['wbi_img']['img_url']
            wbi_sub_url = data['data']['wbi_img']['sub_url']
            
            # 提取文件名（不含扩展名）
            self.wbi_img = wbi_img_url.split('/')[-1].split('.')[0]
            self.wbi_sub = wbi_sub_url.split('/')[-1].split('.')[0]
            
            self.logger.info(f"WBI密钥获取成功: img={self.wbi_img}, sub={self.wbi_sub}")
            return self.wbi_img, self.wbi_sub
            
        except Exception as e:
            self.logger.error(f"获取WBI密钥失败: {e}")
            raise
    
    def _get_mixin_key(self, img_key: str, sub_key: str) -> str:
        """根据img_key和sub_key生成mixin_key"""
        content = img_key + sub_key
        mixin_key = ''.join([content[i] for i in self.mixin_array[:32]])
        return mixin_key
    
    def _enc_wbi(self, params: dict) -> dict:
        """使用WBI加密参数"""
        try:
            img_key, sub_key = self._get_wbi_keys()
            mixin_key = self._get_mixin_key(img_key, sub_key)
            
            # 添加wts参数（当前时间戳）
            params['wts'] = int(time.time())
            
            # 按照参数名排序
            params_sorted = dict(sorted(params.items()))
            
            # 构造待加密字符串
            query = urllib.parse.urlencode(params_sorted)
            
            # 计算w_rid
            hash_obj = hashlib.md5((query + mixin_key).encode())
            params['w_rid'] = hash_obj.hexdigest()
            
            return params
        except Exception as e:
            self.logger.error(f"WBI加密失败: {e}")
            # 返回原始参数，尝试不使用WBI加密
            return params
    
    def get_video_detail(self, bvid: str) -> Dict:
        """获取视频详细信息"""
        try:
            url = f"https://api.bilibili.com/x/web-interface/wbi/view/detail?platform=web&bvid={bvid}"
            encrypted_url = self._enc_wbi(url)
            
            response = self.session.get(encrypted_url)
            response.raise_for_status()
            
            data = response.json()
            if data['code'] != 0:
                raise Exception(f"获取视频详情失败: {data['message']}")
            
            return data['data']
            
        except Exception as e:
            self.logger.error(f"获取视频详情失败: {e}")
            raise
    
    def get_video_playurl(self, bvid: str, cid: int, qn: int = 80) -> Dict:
        """获取视频播放链接
        
        函数级注释：
        - 优先使用 `platform=html5 & download=1 & fnval=16 & fourk=0 & force_host=2` 参数组合，以倾向返回 `durl` 的 MP4 直链。
        - 其中 `force_host=2` 可更倾向选择可直连的 CDN 主机（在部分地区更易得到 mp4 而非 DASH 的 m4s）。
        - 若后续需要更细的兼容，可在调用层补充回退策略（例如再试不同参数或走 yt-dlp）。
        - 增加了多种参数组合的尝试，提高无Cookie情况下的成功率。
        
        Args:
            bvid: 视频BV号
            cid: 视频CID
            qn: 视频质量 (16:流畅 32:清晰 64:高清 74:高清60帧 80:超清 112:高码率 116:超清60帧)
        
        Returns:
            包含视频链接信息的字典
        """
        # 定义多种参数组合，按成功可能性排序
        param_combinations = [
            # 组合1: 基础组合 - html5平台+下载模式
            {
                "platform": "html5",
                "download": 1,
                "fnval": 16,
                "fourk": 0,
                "force_host": 2
            },
            # 组合2: 移动端模拟 - 更容易获取直链
            {
                "platform": "android",
                "fnval": 0,
                "fourk": 0
            },
            # 组合3: 完整DASH支持 - 获取更多格式选择
            {
                "platform": "pc",
                "fnval": 4048,  # 支持所有格式
                "fourk": 1
            }
        ]
        
        last_error = None
        
        # 依次尝试不同参数组合
        for params in param_combinations:
            try:
                # 构建基础参数
                base_params = {
                    'cid': cid,
                    'bvid': bvid,
                    'qn': qn,
                    'type': '',
                    'otype': 'json',
                    'fnver': 0
                }
                # 合并特定参数
                base_params.update(params)
                
                # 使用WBI加密
                encrypted_params = self._enc_wbi(base_params)
                
                # 添加Referer头，提高成功率
                headers = {
                    'Referer': f'https://www.bilibili.com/video/{bvid}',
                    'Origin': 'https://www.bilibili.com'
                }
                
                url = "https://api.bilibili.com/x/player/wbi/playurl"
                response = self.session.get(url, params=encrypted_params, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                if data['code'] == 0:
                    self.logger.info(f"成功获取播放链接，使用参数组合: {params}")
                    return data['data']
                else:
                    self.logger.warning(f"参数组合 {params} 获取失败: {data['message']}")
                    last_error = Exception(f"获取播放链接失败: {data['message']}")
            
            except Exception as e:
                self.logger.warning(f"参数组合 {params} 请求异常: {e}")
                last_error = e
                continue
        
        # 所有组合都失败了
        if last_error:
            self.logger.error(f"所有参数组合均获取播放链接失败: {last_error}")
            raise last_error
        else:
            raise Exception("获取播放链接失败: 未知错误")
    
    def get_best_audio_url(self, bvid: str, cid: int) -> Optional[str]:
        """获取最佳音频链接
        
        函数级注释：
        - 第一步尝试 `durl` 的 MP4 直链（最容易直接访问）。
        - 若无 `durl` 或返回为不可直接访问的格式，则回退到 DASH 音频里选择码率最高且更可能兼容的流。
        - 上游 `get_video_playurl` 已增加 `force_host=2`，此处以日志记录帮助诊断是否仍返回 `m4s`。
        
        Args:
            bvid: 视频BV号
            cid: 视频CID
            
        Returns:
            音频链接URL，如果获取失败返回None
        """
        try:
            playurl_data = self.get_video_playurl(bvid, cid)
            
            # 优先从durl获取MP4链接（直接可访问的格式）
            if 'durl' in playurl_data and playurl_data['durl']:
                mp4_url = playurl_data['durl'][0].get('url')
                if mp4_url and '.mp4' in mp4_url:
                    self.logger.info(f"找到MP4格式音频链接: {mp4_url[:100]}...")
                    return mp4_url
                else:
                    # 记录非mp4的直链情况，便于后续诊断
                    self.logger.info(f"返回的直链并非mp4，可能为flv或其他: {str(mp4_url)[:100]}...")

            # 如果没有durl，再尝试从DASH格式中获取音频
            if 'dash' in playurl_data and playurl_data['dash']:
                dash = playurl_data['dash']
                if 'audio' in dash and dash['audio']:
                    # 优先选择MP4格式的音频
                    audio_list = dash['audio']
                    
                    # 先找MP4格式的音频
                    mp4_audios = [audio for audio in audio_list if 'mp4' in audio.get('mimeType', '').lower()]
                    if mp4_audios:
                        best_audio = max(mp4_audios, key=lambda x: x.get('bandwidth', 0))
                        audio_url = best_audio.get('baseUrl') or best_audio.get('base_url')
                        self.logger.info(f"找到DASH MP4格式音频链接: {audio_url[:100]}...")
                        return audio_url
                    
                    # 如果没有MP4格式，选择码率最高的音频
                    best_audio = max(audio_list, key=lambda x: x.get('bandwidth', 0))
                    audio_url = best_audio.get('baseUrl') or best_audio.get('base_url')
                    self.logger.info(f"找到DASH音频链接: {audio_url[:100]}...")
                    return audio_url
            
            self.logger.warning(f"未找到可用的音频链接: bvid={bvid}, cid={cid}")
            return None
            
        except Exception as e:
            self.logger.error(f"获取音频链接失败: {e}")
            return None
    
    def parse_video_url(self, url: str) -> Optional[str]:
        """从视频URL中提取BV号
        
        Args:
            url: B站视频URL
            
        Returns:
            BV号，如果解析失败返回None
        """
        try:
            # 支持多种B站URL格式
            patterns = [
                r'bilibili\.com/video/([Bb][Vv][0-9A-Za-z]+)',
                r'bilibili\.com/video/([Aa][Vv]\d+)',
                r'b23\.tv/([0-9A-Za-z]+)',
                r'([Bb][Vv][0-9A-Za-z]+)',
                r'([Aa][Vv]\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    video_id = match.group(1)
                    # 如果是AV号，需要转换为BV号
                    if video_id.lower().startswith('av'):
                        # 这里可以实现AV号转BV号的逻辑
                        # 暂时返回None，让调用方使用yt-dlp处理
                        return None
                    return video_id
            
            return None
            
        except Exception as e:
            self.logger.error(f"解析视频URL失败: {e}")
            return None
    
    def get_video_info_with_real_urls(self, url: str) -> Optional[Dict]:
        """获取视频信息和真实播放链接
        
        Args:
            url: B站视频URL
            
        Returns:
            包含视频信息和真实链接的字典
        """
        try:
            bvid = self.parse_video_url(url)
            if not bvid:
                self.logger.warning(f"无法解析视频URL: {url}")
                return None
            
            # 尝试多种API获取视频详情，绕过B站限制
            detail = None
            try:
                # 主API尝试
                detail = self.get_video_detail(bvid)
            except Exception as e1:
                self.logger.warning(f"主API获取视频详情失败: {e1}，尝试备用API")
                try:
                    # 备用API尝试 - 使用不同参数组合
                    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
                    response = self.session.get(url)
                    response.raise_for_status()
                    data = response.json()
                    if data['code'] == 0:
                        detail = {'View': data['data']}
                except Exception as e2:
                    self.logger.error(f"备用API也失败: {e2}")
                    raise e1
            
            if not detail:
                self.logger.error("所有API尝试均失败")
                return None
                
            view_info = detail.get('View', {})
            
            # 获取视频分P信息
            pages = view_info.get('pages', [])
            if not pages:
                self.logger.warning(f"视频没有分P信息: {bvid}")
                return None
            
            # 构建返回数据
            video_info = {
                'bvid': bvid,
                'aid': view_info.get('aid'),
                'title': view_info.get('title', ''),
                'description': view_info.get('desc', ''),
                'uploader': view_info.get('owner', {}).get('name', ''),
                'duration': view_info.get('duration', 0),
                'view_count': view_info.get('stat', {}).get('view', 0),
                'like_count': view_info.get('stat', {}).get('like', 0),
                'upload_date': view_info.get('pubdate', 0),
                'thumbnail': view_info.get('pic', ''),
                'webpage_url': f"https://www.bilibili.com/video/{bvid}",
                'pages': []
            }
            
            # 获取每个分P的真实链接，使用多种方法尝试
            for page in pages:
                cid = page.get('cid')
                if cid:
                    # 尝试多种方式获取音频URL
                    audio_url = None
                    try:
                        audio_url = self.get_best_audio_url(bvid, cid)
                    except Exception as e:
                        self.logger.warning(f"主方法获取音频失败: {e}，尝试备用方法")
                        try:
                            # 备用方法 - 使用不同参数组合
                            params = {
                                'bvid': bvid,
                                'cid': cid,
                                'qn': 80,
                                'fnval': 0,
                                'fnver': 0,
                                'fourk': 0,
                                'platform': 'android'
                            }
                            url = "https://api.bilibili.com/x/player/playurl"
                            response = self.session.get(url, params=params)
                            data = response.json()
                            if data['code'] == 0 and 'durl' in data['data']:
                                audio_url = data['data']['durl'][0].get('url')
                        except Exception:
                            pass
                    
                    page_info = {
                        'part_number': page.get('page', 1),
                        'cid': cid,
                        'title': page.get('part', ''),
                        'duration': page.get('duration', 0),
                        'audio_url': audio_url
                    }
                    video_info['pages'].append(page_info)
            
            return video_info
            
        except Exception as e:
            self.logger.error(f"获取视频信息失败: {e}")
            return None

# 创建全局实例
bilibili_api = BilibiliAPI()