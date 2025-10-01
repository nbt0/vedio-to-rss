# -*- coding: utf-8 -*-
"""
RSS生成器模块

这个模块负责：
1. 将视频信息转换为RSS格式
2. 生成符合RSS 2.0标准的XML
3. 处理单视频和分P视频的不同RSS结构
4. 优化RSS内容以适配AI转写工具
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import logging
from typing import Dict, List
from urllib.parse import quote

class RSSGenerator:
    """RSS生成器类"""
    
    def __init__(self, config, audio_proxy=None):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.rss_config = config.RSS_CONFIG
        self.audio_proxy = audio_proxy
    
    def generate_rss(self, video_info: Dict, original_url: str) -> str:
        """
        生成RSS内容
        
        Args:
            video_info (dict): 视频信息
            original_url (str): 原始视频URL
            
        Returns:
            str: RSS XML内容
        """
        try:
            # 根据配置处理音频URL
            audio_url_mode = self.config.RSS_CONFIG.get('audio_url_mode', 'proxy')
            if audio_url_mode != 'direct' and self.audio_proxy:
                # 获取基础URL
                base_url = f"http://{self.config.HOST}:{self.config.PORT}"
                # 处理音频URL
                self._process_audio_urls(video_info, audio_url_mode, base_url)
            
            # 确保video_info包含type字段
            if 'type' not in video_info:
                # 根据结构判断类型
                if 'videos' in video_info and isinstance(video_info['videos'], list):
                    video_info['type'] = 'playlist'
                else:
                    video_info['type'] = 'single'
                self.logger.info(f"自动设置视频类型为: {video_info['type']}")
            
            if video_info['type'] == 'single':
                return self._generate_single_video_rss(video_info)
            elif video_info['type'] == 'playlist':
                return self._generate_playlist_rss(video_info)
            else:
                raise ValueError(f"不支持的视频类型: {video_info['type']}")
                
        except Exception as e:
            self.logger.error(f"RSS生成失败: {e}")
            raise Exception(f"RSS生成失败: {str(e)}")
    
    def _process_audio_urls(self, video_info: Dict, mode: str, base_url: str) -> None:
        """根据模式处理音频URL"""
        try:
            if video_info['type'] == 'single':
                # 单视频处理
                if video_info.get('audio_url'):
                    original_audio_url = video_info['audio_url']
                    video_info['audio_url'] = self._get_processed_audio_url(original_audio_url, mode, base_url)
                    
            elif video_info['type'] == 'playlist':
                # 播放列表处理
                if 'videos' in video_info:
                    for video in video_info['videos']:
                        if video.get('audio_url'):
                            original_audio_url = video['audio_url']
                            video['audio_url'] = self._get_processed_audio_url(original_audio_url, mode, base_url)
                            
        except Exception as e:
            self.logger.error(f"处理音频URL失败: {e}")
    
    def _get_processed_audio_url(self, original_url: str, mode: str, base_url: str) -> str:
        """根据模式获取处理后的音频URL"""
        try:
            if mode == 'direct':
                return original_url
            elif mode == 'download':
                # 尝试获取本地文件URL
                local_url = self.audio_proxy.get_local_file_url(original_url, base_url)
                if local_url:
                    return local_url
                # 如果本地文件不存在，回退到代理模式
                safe_chars = ':/?#[]@!$&\'()*+,;='
                encoded_url = quote(original_url, safe=safe_chars)
                return self.audio_proxy.get_proxy_url(original_url, base_url) + f"?url={encoded_url}"
            else:  # proxy mode
                safe_chars = ':/?#[]@!$&\'()*+,;='
                encoded_url = quote(original_url, safe=safe_chars)
                return self.audio_proxy.get_proxy_url(original_url, base_url) + f"?url={encoded_url}"
        except Exception as e:
            self.logger.error(f"获取处理后的音频URL失败: {e}")
            return original_url  # 出错时返回原始URL
    
    def _generate_single_video_rss(self, video_info: Dict) -> str:
        """生成单视频RSS"""
        try:
            # 创建RSS根元素
            rss = ET.Element('rss')
            rss.set('version', '2.0')
            rss.set('xmlns:itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
            rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')
            
            # 创建channel元素
            channel = ET.SubElement(rss, 'channel')
            
            # 添加频道基本信息
            self._add_channel_info(channel, video_info)
            
            # 添加视频项目
            item = ET.SubElement(channel, 'item')
            self._add_video_item(item, video_info)
            
            # 格式化XML
            self._indent_xml(rss)
            
            # 转换为字符串
            xml_str = ET.tostring(rss, encoding='unicode', method='xml')
            
            # 添加XML声明
            xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
            return xml_declaration + xml_str
            
        except Exception as e:
            self.logger.error(f"单视频RSS生成失败: {e}")
            raise
    
    def _generate_playlist_rss(self, video_info: Dict) -> str:
        """生成播放列表RSS"""
        try:
            # 创建RSS根元素
            rss = ET.Element('rss')
            rss.set('version', '2.0')
            rss.set('xmlns:itunes', 'http://www.itunes.com/dtds/podcast-1.0.dtd')
            rss.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')
            
            # 创建channel元素
            channel = ET.SubElement(rss, 'channel')
            
            # 添加频道基本信息
            self._add_channel_info(channel, video_info)
            
            # 为每个视频添加item
            for video in video_info['videos']:
                item = ET.SubElement(channel, 'item')
                self._add_playlist_item(item, video, video_info)
            
            # 格式化XML
            self._indent_xml(rss)
            
            # 转换为字符串
            xml_str = ET.tostring(rss, encoding='unicode', method='xml')
            
            # 添加XML声明
            xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
            return xml_declaration + xml_str
            
        except Exception as e:
            self.logger.error(f"播放列表RSS生成失败: {e}")
            raise
    
    def _add_channel_info(self, channel: ET.Element, video_info: Dict) -> None:
        """添加频道基本信息"""
        try:
            # 频道标题
            title = ET.SubElement(channel, 'title')
            title_suffix = self.rss_config.get('title_suffix', ' - 视频转RSS - AI转写专用')
            if video_info['type'] == 'single':
                title.text = f"{video_info['title']}{title_suffix}"
            else:
                title.text = f"{video_info['title']} (共{video_info['video_count']}P){title_suffix}"
            
            # 频道链接
            link = ET.SubElement(channel, 'link')
            link.text = video_info.get('webpage_url', 'http://localhost:5000')
            
            # 频道描述
            description = ET.SubElement(channel, 'description')
            if video_info['type'] == 'playlist':
                # 播放列表特殊描述
                desc_text = f"{video_info.get('description', '')}\n\n" + \
                           f"这是一个包含 {video_info.get('video_count', 0)} 个视频的播放列表，" + \
                           f"总时长约 {self._format_duration(video_info.get('total_duration', 0))}。"
            else:
                desc_text = video_info.get('description', '视频转RSS工具生成的内容')
            
            description_suffix = self.rss_config.get('description_suffix', '')
            if description_suffix:
                desc_text += description_suffix
            if len(desc_text) > 500:
                desc_text = desc_text[:500] + '...'
            description.text = desc_text
            
            # 语言
            language = ET.SubElement(channel, 'language')
            language.text = self.rss_config['language']
            
            # 版权信息
            copyright_elem = ET.SubElement(channel, 'copyright')
            copyright_elem.text = f"{self.rss_config['copyright']} | UP主: {video_info.get('uploader', '未知')}"
            
            # 管理员邮箱
            managing_editor = ET.SubElement(channel, 'managingEditor')
            managing_editor.text = self.rss_config['managing_editor']
            
            # 网站管理员
            web_master = ET.SubElement(channel, 'webMaster')
            web_master.text = self.rss_config['web_master']
            
            # 发布日期
            pub_date = ET.SubElement(channel, 'pubDate')
            pub_date.text = self._format_rfc822_date(datetime.now(timezone.utc))
            
            # 最后构建日期
            last_build_date = ET.SubElement(channel, 'lastBuildDate')
            last_build_date.text = self._format_rfc822_date(datetime.now(timezone.utc))
            
            # 生成器
            generator = ET.SubElement(channel, 'generator')
            generator.text = self.rss_config['generator']
            
            # 文档链接
            docs = ET.SubElement(channel, 'docs')
            docs.text = self.rss_config['docs']
            
            # TTL
            ttl = ET.SubElement(channel, 'ttl')
            ttl.text = str(self.rss_config['ttl'])
            
            # 分类
            category = ET.SubElement(channel, 'category')
            category.text = self.rss_config['category']
            
            # 图片（如果有缩略图）
            if video_info.get('thumbnail'):
                image = ET.SubElement(channel, 'image')
                image_url = ET.SubElement(image, 'url')
                image_url.text = video_info['thumbnail']
                image_title = ET.SubElement(image, 'title')
                image_title.text = title.text
                image_link = ET.SubElement(image, 'link')
                image_link.text = link.text
            
            # iTunes标签（用于播客兼容性）
            itunes_author = ET.SubElement(channel, 'itunes:author')
            itunes_author.text = video_info.get('uploader', '未知UP主')
            
            itunes_summary = ET.SubElement(channel, 'itunes:summary')
            itunes_summary.text = description.text
            
            itunes_category = ET.SubElement(channel, 'itunes:category')
            itunes_category.set('text', 'Technology')
            
        except Exception as e:
            self.logger.error(f"添加频道信息失败: {e}")
            raise
    
    def _add_video_item(self, item: ET.Element, video_info: Dict) -> None:
        """添加单视频项目"""
        try:
            # 标题
            title = ET.SubElement(item, 'title')
            title.text = video_info['title']
            
            # 链接
            link = ET.SubElement(item, 'link')
            link.text = video_info.get('webpage_url', '')
            
            # 描述
            description = ET.SubElement(item, 'description')
            desc_text = self._create_item_description(video_info)
            description.text = desc_text
            
            # GUID
            guid = ET.SubElement(item, 'guid')
            guid.text = video_info.get('id', video_info.get('webpage_url', ''))
            guid.set('isPermaLink', 'false')
            
            # 发布日期
            pub_date = ET.SubElement(item, 'pubDate')
            upload_date = video_info.get('upload_date', '')
            if upload_date:
                try:
                    date_obj = datetime.strptime(upload_date, '%Y%m%d')
                    pub_date.text = self._format_rfc822_date(date_obj.replace(tzinfo=timezone.utc))
                except:
                    pub_date.text = self._format_rfc822_date(datetime.now(timezone.utc))
            else:
                pub_date.text = self._format_rfc822_date(datetime.now(timezone.utc))
            
            # 音频附件（关键部分）
            audio_url = video_info.get('audio_url')
            if not audio_url:
                # 如果没有直接的audio_url，尝试从formats中提取
                formats = video_info.get('formats', [])
                for fmt in formats:
                    if fmt.get('acodec') != 'none' and fmt.get('url'):
                        audio_url = fmt['url']
                        break
            
            if audio_url:
                enclosure = ET.SubElement(item, 'enclosure')
                enclosure.set('url', audio_url)
                enclosure.set('type', 'audio/mpeg')
                enclosure.set('length', '0')
            else:
                # 如果没有音频URL，添加默认enclosure
                enclosure = ET.SubElement(item, 'enclosure')
                enclosure.set('url', '')
                enclosure.set('type', 'audio/mpeg')
                enclosure.set('length', '0')
            
            # iTunes标签
            itunes_author = ET.SubElement(item, 'itunes:author')
            itunes_author.text = video_info.get('uploader', '未知UP主')
            
            itunes_duration = ET.SubElement(item, 'itunes:duration')
            itunes_duration.text = self._format_duration(video_info.get('duration', 0))
            
            itunes_summary = ET.SubElement(item, 'itunes:summary')
            itunes_summary.text = desc_text
            
        except Exception as e:
            self.logger.error(f"添加视频项目失败: {e}")
            raise
    
    def _add_playlist_item(self, item: ET.Element, video: Dict, playlist_info: Dict) -> None:
        """添加播放列表中的视频项目"""
        try:
            # 标题
            title = ET.SubElement(item, 'title')
            title.text = f"P{video['part_number']}: {video['title']}"
            
            # 链接
            link = ET.SubElement(item, 'link')
            link.text = video.get('webpage_url', '')
            
            # 描述
            description = ET.SubElement(item, 'description')
            desc_text = self._create_playlist_item_description(video, playlist_info)
            description.text = desc_text
            
            # GUID
            guid = ET.SubElement(item, 'guid')
            guid.text = f"{playlist_info.get('id', '')}_P{video['part_number']}"
            guid.set('isPermaLink', 'false')
            
            # 发布日期
            pub_date = ET.SubElement(item, 'pubDate')
            upload_date = playlist_info.get('upload_date', '')
            if upload_date:
                try:
                    date_obj = datetime.strptime(upload_date, '%Y%m%d')
                    pub_date.text = self._format_rfc822_date(date_obj.replace(tzinfo=timezone.utc))
                except:
                    pub_date.text = self._format_rfc822_date(datetime.now(timezone.utc))
            else:
                pub_date.text = self._format_rfc822_date(datetime.now(timezone.utc))
            
            # 音频附件
            if video.get('audio_url'):
                enclosure = ET.SubElement(item, 'enclosure')
                enclosure.set('url', video['audio_url'])
                enclosure.set('type', 'audio/mpeg')
                enclosure.set('length', '0')  # 播放列表中通常没有详细的文件大小信息
            
            # iTunes标签
            itunes_author = ET.SubElement(item, 'itunes:author')
            itunes_author.text = playlist_info.get('uploader', '未知UP主')
            
            itunes_duration = ET.SubElement(item, 'itunes:duration')
            itunes_duration.text = self._format_duration(video.get('duration', 0))
            
            itunes_summary = ET.SubElement(item, 'itunes:summary')
            itunes_summary.text = desc_text
            
        except Exception as e:
            self.logger.error(f"添加播放列表项目失败: {e}")
            raise
    
    def _create_item_description(self, video_info: Dict) -> str:
        """创建视频项目描述"""
        try:
            desc_parts = []
            
            # 基本信息
            if video_info.get('description'):
                desc_parts.append(video_info['description'][:300] + ('...' if len(video_info['description']) > 300 else ''))
            
            # 视频统计
            stats = []
            if video_info.get('duration'):
                stats.append(f"时长: {self._format_duration(video_info['duration'])}")
            if video_info.get('view_count'):
                stats.append(f"播放: {self._format_number(video_info['view_count'])}")
            if video_info.get('like_count'):
                stats.append(f"点赞: {self._format_number(video_info['like_count'])}")
            
            if stats:
                desc_parts.append(' | '.join(stats))
            
            # 平台信息
            platform_name = self.config.SUPPORTED_PLATFORMS.get(video_info['platform'], {}).get('name', video_info['platform'])
            desc_parts.append(f"来源: {platform_name}")
            
            # AI转写提示
            desc_parts.append("\n--- AI转写说明 ---")
            desc_parts.append("此RSS已优化用于AI音频转写工具，音频文件可直接用于语音识别和内容分析。")
            
            return '\n\n'.join(desc_parts)
            
        except Exception as e:
            self.logger.error(f"创建项目描述失败: {e}")
            return video_info.get('title', '无描述')
    
    def _create_playlist_item_description(self, video: Dict, playlist_info: Dict) -> str:
        """创建播放列表项目描述"""
        try:
            desc_parts = []
            
            # 分P信息
            desc_parts.append(f"这是《{playlist_info['title']}》的第 {video['part_number']} 部分")
            
            # 视频描述
            if video.get('description'):
                desc_parts.append(video['description'][:200] + ('...' if len(video['description']) > 200 else ''))
            
            # 时长信息
            if video.get('duration'):
                desc_parts.append(f"时长: {self._format_duration(video['duration'])}")
            
            # 播放列表统计
            desc_parts.append(f"播放列表共 {playlist_info['video_count']} 个视频")
            
            # 平台信息
            platform_name = self.config.SUPPORTED_PLATFORMS.get(playlist_info['platform'], {}).get('name', playlist_info['platform'])
            desc_parts.append(f"来源: {platform_name}")
            
            return '\n\n'.join(desc_parts)
            
        except Exception as e:
            self.logger.error(f"创建播放列表项目描述失败: {e}")
            return video.get('title', '无描述')
    
    def _format_duration(self, seconds) -> str:
        """格式化时长"""
        if not seconds:
            return '00:00'
        
        # 确保seconds是整数类型
        seconds = int(float(seconds)) if seconds else 0
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    def _format_number(self, num: int) -> str:
        """格式化数字"""
        if num >= 10000:
            return f"{num/10000:.1f}万"
        elif num >= 1000:
            return f"{num/1000:.1f}k"
        else:
            return str(num)
    
    def _format_rfc822_date(self, dt: datetime) -> str:
        """格式化RFC822日期"""
        return dt.strftime('%a, %d %b %Y %H:%M:%S %z')
    
    def _indent_xml(self, elem: ET.Element, level: int = 0) -> None:
        """格式化XML缩进"""
        indent = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            for child in elem:
                self._indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent
    
    def validate_rss(self, rss_content: str) -> bool:
        """验证RSS内容是否有效"""
        try:
            ET.fromstring(rss_content)
            return True
        except ET.ParseError as e:
            self.logger.error(f"RSS验证失败: {e}")
            return False
    
    def get_rss_info(self, rss_content: str) -> Dict:
        """从RSS内容中提取基本信息"""
        try:
            root = ET.fromstring(rss_content)
            channel = root.find('channel')
            
            if channel is None:
                return {}
            
            info = {
                'title': channel.findtext('title', ''),
                'description': channel.findtext('description', ''),
                'link': channel.findtext('link', ''),
                'item_count': len(channel.findall('item')),
                'pub_date': channel.findtext('pubDate', ''),
                'generator': channel.findtext('generator', '')
            }
            
            return info
            
        except Exception as e:
            self.logger.error(f"提取RSS信息失败: {e}")
            return {}