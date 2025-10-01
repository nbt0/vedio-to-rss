#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缓存管理模块
提供视频信息、API响应等数据的缓存功能
"""

import hashlib
import json
import os
import pickle
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union
from threading import Lock
import threading

from .exceptions import CacheError
from .logger import get_logger


class CacheItem:
    """缓存项"""
    
    def __init__(self, key: str, value: Any, expire_time: Optional[datetime] = None):
        self.key = key
        self.value = value
        self.created_at = datetime.now()
        self.expire_time = expire_time
        self.access_count = 0
        self.last_accessed = self.created_at
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expire_time is None:
            return False
        return datetime.now() > self.expire_time
    
    def access(self) -> Any:
        """访问缓存项"""
        self.access_count += 1
        self.last_accessed = datetime.now()
        return self.value
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'key': self.key,
            'value': self.value,
            'created_at': self.created_at.isoformat(),
            'expire_time': self.expire_time.isoformat() if self.expire_time else None,
            'access_count': self.access_count,
            'last_accessed': self.last_accessed.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CacheItem':
        """从字典创建缓存项"""
        item = cls(
            key=data['key'],
            value=data['value'],
            expire_time=datetime.fromisoformat(data['expire_time']) if data['expire_time'] else None
        )
        item.created_at = datetime.fromisoformat(data['created_at'])
        item.access_count = data['access_count']
        item.last_accessed = datetime.fromisoformat(data['last_accessed'])
        return item


class MemoryCache:
    """内存缓存"""
    
    def __init__(self, max_size: int = 100, default_expire_hours: int = 24):
        self.max_size = max_size
        self.default_expire_hours = default_expire_hours
        self._cache: Dict[str, CacheItem] = {}
        self._lock = Lock()
        self.logger = get_logger('cache.memory')
    
    def _generate_key(self, key: Union[str, Dict, tuple]) -> str:
        """生成缓存键"""
        if isinstance(key, str):
            return key
        elif isinstance(key, (dict, tuple, list)):
            # 对复杂对象生成哈希键
            key_str = json.dumps(key, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(key_str.encode('utf-8')).hexdigest()
        else:
            return str(key)
    
    def get(self, key: Union[str, Dict, tuple]) -> Optional[Any]:
        """获取缓存值"""
        cache_key = self._generate_key(key)
        
        with self._lock:
            if cache_key not in self._cache:
                return None
            
            item = self._cache[cache_key]
            
            # 检查是否过期
            if item.is_expired():
                del self._cache[cache_key]
                self.logger.debug(f"缓存项已过期并被删除: {cache_key}")
                return None
            
            # 访问缓存项
            value = item.access()
            self.logger.debug(f"缓存命中: {cache_key}")
            return value
    
    def set(self, key: Union[str, Dict, tuple], value: Any, 
            expire_hours: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            cache_key = self._generate_key(key)
            expire_hours = expire_hours or self.default_expire_hours
            expire_time = datetime.now() + timedelta(hours=expire_hours)
            
            with self._lock:
                # 如果缓存已满，删除最旧的项
                if len(self._cache) >= self.max_size and cache_key not in self._cache:
                    self._evict_oldest()
                
                # 创建缓存项
                item = CacheItem(cache_key, value, expire_time)
                self._cache[cache_key] = item
                
                self.logger.debug(f"缓存已设置: {cache_key}, 过期时间: {expire_time}")
                return True
                
        except Exception as e:
            self.logger.error(f"设置缓存失败: {str(e)}")
            raise CacheError(f"Failed to set cache: {str(e)}", cache_key)
    
    def delete(self, key: Union[str, Dict, tuple]) -> bool:
        """删除缓存项"""
        cache_key = self._generate_key(key)
        
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                self.logger.debug(f"缓存项已删除: {cache_key}")
                return True
            return False
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self.logger.info(f"已清空所有缓存，共删除 {count} 项")
    
    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        with self._lock:
            expired_keys = []
            for key, item in self._cache.items():
                if item.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                self.logger.info(f"清理过期缓存 {len(expired_keys)} 项")
            
            return len(expired_keys)
    
    def _evict_oldest(self) -> None:
        """删除最旧的缓存项"""
        if not self._cache:
            return
        
        # 找到最旧的项（最少访问或最早创建）
        oldest_key = min(self._cache.keys(), 
                        key=lambda k: (self._cache[k].access_count, self._cache[k].created_at))
        
        del self._cache[oldest_key]
        self.logger.debug(f"删除最旧缓存项: {oldest_key}")
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        with self._lock:
            total_items = len(self._cache)
            expired_items = sum(1 for item in self._cache.values() if item.is_expired())
            
            return {
                'total_items': total_items,
                'expired_items': expired_items,
                'valid_items': total_items - expired_items,
                'max_size': self.max_size,
                'usage_ratio': total_items / self.max_size if self.max_size > 0 else 0
            }


class FileCache:
    """文件缓存"""
    
    def __init__(self, cache_dir: str, default_expire_hours: int = 24):
        self.cache_dir = cache_dir
        self.default_expire_hours = default_expire_hours
        self._lock = Lock()
        self.logger = get_logger('cache.file')
        
        # 确保缓存目录存在
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_file_path(self, key: str) -> str:
        """获取缓存文件路径"""
        # 使用哈希避免文件名过长或包含特殊字符
        safe_key = hashlib.md5(key.encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"{safe_key}.cache")
    
    def _get_meta_file_path(self, key: str) -> str:
        """获取元数据文件路径"""
        safe_key = hashlib.md5(key.encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"{safe_key}.meta")
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        cache_file = self._get_cache_file_path(key)
        meta_file = self._get_meta_file_path(key)
        
        try:
            with self._lock:
                if not os.path.exists(cache_file) or not os.path.exists(meta_file):
                    return None
                
                # 读取元数据
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                # 检查是否过期
                if meta.get('expire_time'):
                    expire_time = datetime.fromisoformat(meta['expire_time'])
                    if datetime.now() > expire_time:
                        self._delete_cache_files(cache_file, meta_file)
                        self.logger.debug(f"文件缓存已过期并被删除: {key}")
                        return None
                
                # 读取缓存数据
                with open(cache_file, 'rb') as f:
                    value = pickle.load(f)
                
                # 更新访问信息
                meta['access_count'] = meta.get('access_count', 0) + 1
                meta['last_accessed'] = datetime.now().isoformat()
                
                with open(meta_file, 'w', encoding='utf-8') as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                
                self.logger.debug(f"文件缓存命中: {key}")
                return value
                
        except Exception as e:
            self.logger.error(f"读取文件缓存失败: {str(e)}")
            # 清理可能损坏的缓存文件
            self._delete_cache_files(cache_file, meta_file)
            return None
    
    def set(self, key: str, value: Any, expire_hours: Optional[int] = None) -> bool:
        """设置缓存值"""
        cache_file = self._get_cache_file_path(key)
        meta_file = self._get_meta_file_path(key)
        
        try:
            expire_hours = expire_hours or self.default_expire_hours
            expire_time = datetime.now() + timedelta(hours=expire_hours)
            
            with self._lock:
                # 写入缓存数据
                with open(cache_file, 'wb') as f:
                    pickle.dump(value, f)
                
                # 写入元数据
                meta = {
                    'key': key,
                    'created_at': datetime.now().isoformat(),
                    'expire_time': expire_time.isoformat(),
                    'access_count': 0,
                    'last_accessed': datetime.now().isoformat()
                }
                
                with open(meta_file, 'w', encoding='utf-8') as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                
                self.logger.debug(f"文件缓存已设置: {key}, 过期时间: {expire_time}")
                return True
                
        except Exception as e:
            self.logger.error(f"设置文件缓存失败: {str(e)}")
            # 清理可能不完整的缓存文件
            self._delete_cache_files(cache_file, meta_file)
            raise CacheError(f"Failed to set file cache: {str(e)}", key)
    
    def delete(self, key: str) -> bool:
        """删除缓存项"""
        cache_file = self._get_cache_file_path(key)
        meta_file = self._get_meta_file_path(key)
        
        with self._lock:
            deleted = self._delete_cache_files(cache_file, meta_file)
            if deleted:
                self.logger.debug(f"文件缓存项已删除: {key}")
            return deleted
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            count = 0
            for filename in os.listdir(self.cache_dir):
                if filename.endswith(('.cache', '.meta')):
                    file_path = os.path.join(self.cache_dir, filename)
                    try:
                        os.remove(file_path)
                        count += 1
                    except Exception as e:
                        self.logger.warning(f"删除缓存文件失败: {file_path}, {str(e)}")
            
            self.logger.info(f"已清空所有文件缓存，共删除 {count} 个文件")
    
    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        with self._lock:
            cleaned_count = 0
            
            for filename in os.listdir(self.cache_dir):
                if not filename.endswith('.meta'):
                    continue
                
                meta_file = os.path.join(self.cache_dir, filename)
                cache_file = meta_file.replace('.meta', '.cache')
                
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    
                    if meta.get('expire_time'):
                        expire_time = datetime.fromisoformat(meta['expire_time'])
                        if datetime.now() > expire_time:
                            self._delete_cache_files(cache_file, meta_file)
                            cleaned_count += 1
                            
                except Exception as e:
                    self.logger.warning(f"检查缓存文件过期状态失败: {meta_file}, {str(e)}")
                    # 删除损坏的缓存文件
                    self._delete_cache_files(cache_file, meta_file)
                    cleaned_count += 1
            
            if cleaned_count > 0:
                self.logger.info(f"清理过期文件缓存 {cleaned_count} 项")
            
            return cleaned_count
    
    def _delete_cache_files(self, cache_file: str, meta_file: str) -> bool:
        """删除缓存文件和元数据文件"""
        deleted = False
        
        for file_path in [cache_file, meta_file]:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    deleted = True
                except Exception as e:
                    self.logger.warning(f"删除缓存文件失败: {file_path}, {str(e)}")
        
        return deleted
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        with self._lock:
            total_files = 0
            expired_files = 0
            total_size = 0
            
            for filename in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, filename)
                
                if filename.endswith('.cache'):
                    total_files += 1
                    total_size += os.path.getsize(file_path)
                    
                    # 检查对应的meta文件
                    meta_file = file_path.replace('.cache', '.meta')
                    if os.path.exists(meta_file):
                        try:
                            with open(meta_file, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                            
                            if meta.get('expire_time'):
                                expire_time = datetime.fromisoformat(meta['expire_time'])
                                if datetime.now() > expire_time:
                                    expired_files += 1
                        except Exception:
                            expired_files += 1  # 损坏的文件也算过期
            
            return {
                'total_files': total_files,
                'expired_files': expired_files,
                'valid_files': total_files - expired_files,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }


class VideoCache:
    """视频缓存管理器（结合内存和文件缓存）"""
    
    def __init__(self, cache_dir: str, memory_cache_size: int = 50, 
                 default_expire_hours: int = 24):
        self.memory_cache = MemoryCache(memory_cache_size, default_expire_hours)
        self.file_cache = FileCache(cache_dir, default_expire_hours)
        self.logger = get_logger('cache.video')
        
        # 启动清理线程
        self._start_cleanup_thread()
    
    def get_video_info(self, url: str) -> Optional[Dict]:
        """获取视频信息缓存"""
        cache_key = f"video_info:{url}"
        
        # 先尝试内存缓存
        result = self.memory_cache.get(cache_key)
        if result is not None:
            return result
        
        # 再尝试文件缓存
        result = self.file_cache.get(cache_key)
        if result is not None:
            # 将文件缓存的结果放入内存缓存
            self.memory_cache.set(cache_key, result, expire_hours=1)  # 内存缓存1小时
            return result
        
        return None
    
    def set_video_info(self, url: str, info: Dict, expire_hours: int = 24) -> bool:
        """设置视频信息缓存"""
        cache_key = f"video_info:{url}"
        
        try:
            # 同时设置内存和文件缓存
            memory_success = self.memory_cache.set(cache_key, info, 
                                                 expire_hours=min(expire_hours, 1))  # 内存缓存最多1小时
            file_success = self.file_cache.set(cache_key, info, expire_hours)
            
            return memory_success and file_success
            
        except Exception as e:
            self.logger.error(f"设置视频信息缓存失败: {str(e)}")
            return False
    
    def get_api_response(self, api_key: str) -> Optional[Any]:
        """获取API响应缓存"""
        cache_key = f"api_response:{api_key}"
        return self.memory_cache.get(cache_key)
    
    def set_api_response(self, api_key: str, response: Any, expire_hours: int = 1) -> bool:
        """设置API响应缓存（仅内存缓存，短期有效）"""
        cache_key = f"api_response:{api_key}"
        return self.memory_cache.set(cache_key, response, expire_hours)
    
    def clear_all(self) -> None:
        """清空所有缓存"""
        self.memory_cache.clear()
        self.file_cache.clear()
        self.logger.info("已清空所有缓存")
    
    def cleanup_expired(self) -> Dict[str, int]:
        """清理过期缓存"""
        memory_cleaned = self.memory_cache.cleanup_expired()
        file_cleaned = self.file_cache.cleanup_expired()
        
        return {
            'memory_cleaned': memory_cleaned,
            'file_cleaned': file_cleaned,
            'total_cleaned': memory_cleaned + file_cleaned
        }
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        memory_stats = self.memory_cache.get_stats()
        file_stats = self.file_cache.get_stats()
        
        return {
            'memory_cache': memory_stats,
            'file_cache': file_stats
        }
    
    def _start_cleanup_thread(self) -> None:
        """启动清理线程"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(3600)  # 每小时清理一次
                    self.cleanup_expired()
                except Exception as e:
                    self.logger.error(f"缓存清理线程出错: {str(e)}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        self.logger.info("缓存清理线程已启动")


# 全局缓存实例
_video_cache = None


def get_video_cache(cache_dir: str = None) -> VideoCache:
    """获取全局视频缓存实例"""
    global _video_cache
    
    if _video_cache is None:
        if cache_dir is None:
            from config import config_manager
            cache_dir = config_manager.get_setting('CACHE_DIR', 'cache')
        
        _video_cache = VideoCache(cache_dir)
    
    return _video_cache


# 缓存装饰器
def cache_result(expire_hours: int = 24, cache_key_func=None):
    """
    缓存函数结果的装饰器
    
    Args:
        expire_hours: 缓存过期时间（小时）
        cache_key_func: 自定义缓存键生成函数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if cache_key_func:
                cache_key = cache_key_func(*args, **kwargs)
            else:
                # 默认使用函数名和参数生成键
                key_data = {
                    'function': func.__name__,
                    'args': args,
                    'kwargs': kwargs
                }
                cache_key = f"func_result:{hashlib.md5(str(key_data).encode()).hexdigest()}"
            
            # 尝试从缓存获取
            cache = get_video_cache()
            result = cache.memory_cache.get(cache_key)
            
            if result is not None:
                return result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache.memory_cache.set(cache_key, result, expire_hours)
            
            return result
        
        return wrapper
    return decorator