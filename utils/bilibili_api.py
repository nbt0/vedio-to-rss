# -*- coding: utf-8 -*-
"""
B站API模块

这个模块负责：
1. 通过B站API获取视频信息
2. 获取真实的播放链接（绕过DASH分片）
3. 处理WBI加密和参数签名
4. 提供多种参数组合以提高成功率
"""

import re
import time
import hashlib
import urllib.parse
import requests
import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, parse_qs


class BilibiliAPI:
    """B站API客户端"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        
        # 优化网络配置，减少超时时间
        self.session.timeout = (3, 8)  # 连接超时3秒，读取超时8秒
        
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Origin': 'https://www.bilibili.com',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site'
        })
        
        # 设置基础Cookie来绕过登录检查
        self.session.cookies.update({
            'buvid3': '12345678-1234-1234-1234-123456789012',
            'b_nut': str(int(time.time())),
            'buvid4': '12345678-1234-1234-1234-123456789012',
            '_uuid': '12345678-1234-1234-1234-123456789012',
            'bsource': '5000'
        })
        
        # 缓存WBI密钥，避免重复获取
        self._wbi_cache = {'keys': None, 'expire_time': 0}
    
    def _make_request(self, url: str, params: dict = None, timeout: int = 5) -> Dict:
        """统一的请求方法，优化超时配置"""
        try:
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            self.logger.warning(f"请求超时: {url}")
            raise Exception("请求超时")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"请求失败: {e}")
            raise Exception(f"网络请求失败: {e}")
    
    def _get_wbi_keys(self) -> tuple:
        """获取WBI密钥，使用缓存机制"""
        current_time = time.time()
        
        # 检查缓存是否有效（缓存10分钟）
        if self._wbi_cache['keys'] and current_time < self._wbi_cache['expire_time']:
            return self._wbi_cache['keys']
        
        try:
            # 快速获取WBI密钥，减少超时时间
            data = self._make_request("https://api.bilibili.com/x/web-interface/nav", timeout=3)
            
            if data.get('code') != 0:
                raise Exception(f"获取WBI密钥失败: {data.get('message', '未知错误')}")
            
            wbi_img = data['data']['wbi_img']
            img_key = wbi_img['img_url'].split('/')[-1].split('.')[0]
            sub_key = wbi_img['sub_url'].split('/')[-1].split('.')[0]
            
            # 更新缓存
            self._wbi_cache['keys'] = (img_key, sub_key)
            self._wbi_cache['expire_time'] = current_time + 600  # 缓存10分钟
            
            return img_key, sub_key
        except Exception as e:
            self.logger.warning(f"获取WBI密钥失败: {e}")
            # 返回默认密钥，避免完全失败
            return ('default_img_key', 'default_sub_key')
    
    def _get_mixin_key(self, img_key: str, sub_key: str) -> str:
        """获取混合密钥"""
        s = img_key + sub_key
        return ''.join([s[i] for i in [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13]])[:32]
    
    def _enc_wbi(self, params: dict) -> dict:
        """WBI加密，添加快速失败机制"""
        try:
            img_key, sub_key = self._get_wbi_keys()
            if img_key == 'default_img_key':
                # 使用默认密钥时，跳过WBI加密
                return params
                
            mixin_key = self._get_mixin_key(img_key, sub_key)
            curr_time = round(time.time())
            params['wts'] = curr_time
            
            # 对参数进行排序和编码
            query = urllib.parse.urlencode(sorted(params.items()))
            wbi_sign = hashlib.md5((query + mixin_key).encode()).hexdigest()
            params['w_rid'] = wbi_sign
            
            return params
        except Exception as e:
            self.logger.warning(f"WBI加密失败，使用原始参数: {e}")
            return params
    
    def get_video_detail(self, bvid: str) -> Dict:
        """获取视频详情，优化超时配置"""
        try:
            params = {'bvid': bvid}
            # 快速获取视频详情，减少超时时间
            data = self._make_request("https://api.bilibili.com/x/web-interface/view", params, timeout=5)
            
            self.logger.debug(f"获取视频详情响应: {data}")
            
            if data is None:
                self.logger.error("获取视频详情返回None")
                raise Exception("获取视频详情返回None")
            
            if data.get('code') != 0:
                raise Exception(f"获取视频详情失败: {data.get('message', '未知错误')}")
            
            return data.get('data')
        except Exception as e:
            self.logger.error(f"获取视频详情失败: {e}")
            raise
    
    def get_video_playurl(self, bvid: str, cid: int, qn: int = 80) -> Dict:
        """获取视频播放链接，优先返回直接MP4链接，使用快速模式"""
        # 简化参数组合，优先使用最快的方式
        param_combinations = [
            # 组合1: 最简单的请求，不使用WBI加密
            {
                "platform": "html5",
                "fnval": 1,
                "fourk": 0,
                "no_wbi": True
            },
            # 组合2: 移动端模拟 - 更容易获取直链
            {
                "platform": "android",
                "fnval": 0,
                "fourk": 0,
                "no_wbi": True
            },
            # 组合3: 基础组合 - html5平台+下载模式
            {
                "platform": "html5",
                "download": 1,
                "fnval": 16,
                "fourk": 0,
                "force_host": 2
            }
        ]
        
        last_error = None
        
        # 依次尝试不同参数组合，但限制尝试次数
        for i, params in enumerate(param_combinations):
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
                
                # 检查是否需要WBI加密
                no_wbi = params.pop('no_wbi', False)
                base_params.update(params)
                
                # 选择URL和参数处理方式
                if no_wbi:
                    # 使用旧版API，不需要WBI加密
                    url = "https://api.bilibili.com/x/player/playurl"
                    final_params = base_params
                else:
                    # 使用新版API，需要WBI加密
                    url = "https://api.bilibili.com/x/player/wbi/playurl"
                    encrypted_params = self._enc_wbi(base_params)
                    final_params = encrypted_params
                
                self.logger.info(f"尝试参数组合 {i+1}: {params}")
                
                # 快速请求，减少超时时间
                timeout = 3 if i == 0 else 5  # 第一次尝试用最短超时
                data = self._make_request(url, final_params, timeout)
                
                if data.get('code') == 0:
                    self.logger.info(f"参数组合 {i+1} 成功获取播放链接")
                    return data['data']
                else:
                    error_msg = data.get('message', '未知错误')
                    self.logger.warning(f"参数组合 {i+1} 失败: {error_msg}")
                    last_error = error_msg
                    
            except Exception as e:
                self.logger.warning(f"参数组合 {i+1} 异常: {e}")
                last_error = str(e)
                continue
        
        # 所有组合都失败
        raise Exception(f"获取播放链接失败，最后错误: {last_error}")

    def get_best_video_url(self, bvid: str, cid: int, qn: int = 80) -> Optional[str]:
        """获取最佳视频URL，优先返回直接MP4链接"""
        try:
            playurl_data = self.get_video_playurl(bvid, cid, qn)
            
            # 优先检查durl字段（直接MP4链接）
            if 'durl' in playurl_data and playurl_data['durl']:
                durl_list = playurl_data['durl']
                if durl_list and len(durl_list) > 0:
                    # 获取第一个durl的URL
                    video_url = durl_list[0].get('url', '')
                    if video_url and '.mp4' in video_url:  # 修改检查条件，包含.mp4即可
                        self.logger.info(f"成功获取直接MP4链接: {video_url[:100]}...")
                        return video_url
            
            # 如果没有durl，尝试从dash中获取视频流
            if 'dash' in playurl_data and playurl_data['dash']:
                dash_data = playurl_data['dash']
                video_streams = dash_data.get('video', [])
                
                if video_streams:
                    # 按质量排序，选择最高质量的视频流
                    video_streams.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)
                    best_video = video_streams[0]
                    video_url = best_video.get('baseUrl') or best_video.get('base_url', '')
                    
                    if video_url:
                        self.logger.info(f"获取DASH视频流: {video_url[:100]}...")
                        return video_url
            
            self.logger.warning("未找到可用的视频URL")
            return None
            
        except Exception as e:
            self.logger.error(f"获取视频URL失败: {e}")
            return None
    
    def get_best_audio_url(self, bvid: str, cid: int, qn: int = 80) -> Optional[str]:
        """获取最佳音频URL"""
        try:
            playurl_data = self.get_video_playurl(bvid, cid, qn)
            
            # 检查dash中的音频流
            if 'dash' in playurl_data and playurl_data['dash']:
                dash_data = playurl_data['dash']
                audio_streams = dash_data.get('audio', [])
                
                if audio_streams:
                    # 优先选择MP4格式的音频，然后按带宽排序
                    mp4_audio = [a for a in audio_streams if 'mp4' in a.get('mimeType', '').lower()]
                    if mp4_audio:
                        mp4_audio.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)
                        best_audio = mp4_audio[0]
                    else:
                        # 如果没有MP4音频，选择带宽最高的
                        audio_streams.sort(key=lambda x: x.get('bandwidth', 0), reverse=True)
                        best_audio = audio_streams[0]
                    
                    audio_url = best_audio.get('baseUrl') or best_audio.get('base_url', '')
                    if audio_url:
                        self.logger.info(f"获取音频流: {audio_url[:100]}...")
                        return audio_url
            
            self.logger.warning("未找到可用的音频URL")
            return None
            
        except Exception as e:
            self.logger.error(f"获取音频URL失败: {e}")
            return None
    
    def parse_video_url(self, url: str) -> Optional[str]:
        """从视频URL中提取BV号或AV号"""
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
                    # 确保BV号格式正确
                    if video_id.upper().startswith('BV'):
                        return video_id
                    elif video_id.upper().startswith('AV'):
                        return video_id
            
            self.logger.warning(f"无法从URL中提取视频ID: {url}")
            return None
            
        except Exception as e:
            self.logger.error(f"解析视频URL失败: {e}")
            return None


# 创建全局实例
bilibili_api = BilibiliAPI()