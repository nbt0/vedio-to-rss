# 🎵 视频转RSS工具 (Video-to-RSS Tool)

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个高性能的视频转RSS工具，专为AI音频转写和播客订阅而设计。支持YouTube、Bilibili等主流平台，具备**秒级解析速度**和智能缓存机制。

## ✨ 核心特性

### 🚀 极速解析性能
- **2小时视频仅需2.2秒解析** - 媲美SnapAny插件的解析速度
- **智能模式切换** - 快速模式vs完整模式，按需选择
- **会话级超时优化** - 3秒连接，8秒读取，避免长时间等待
- **WBI密钥缓存** - 10分钟缓存机制，减少重复请求

### 🎯 多平台支持
- **Bilibili** - 突破DASH分片限制，获取直接MP4链接
- **YouTube** - 完整的yt-dlp集成，支持各种格式
- **通用支持** - 支持大部分主流视频平台

### 🛠️ 技术亮点
- **WBI加密破解** - 自动处理B站API加密参数
- **DASH分片过滤** - 智能识别并过滤不可播放的分片链接
- **多重回退机制** - API失败时自动切换到备用方案
- **内置代理服务** - 解决跨域和访问限制问题

### 🎨 用户体验
- **友好的Web界面** - 简洁直观的操作界面
- **一键启动脚本** - Windows下双击即可运行
- **详细错误提示** - 清晰的错误信息和解决建议
- **实时日志显示** - 方便调试和问题排查

## 📦 快速开始

### 环境要求
- Python 3.8+
- Windows/Linux/macOS
- 网络连接

### 一键安装（推荐）

**Windows用户：**
```bash
# 克隆项目并启动
git clone https://github.com/yourusername/video-to-rss-tool.git
cd video-to-rss-tool
start.bat
```

**PowerShell用户：**
```powershell
git clone https://github.com/yourusername/video-to-rss-tool.git; cd video-to-rss-tool; .\start.bat
```

### 手动安装

1. **克隆项目**
```bash
git clone https://github.com/yourusername/video-to-rss-tool.git
cd video-to-rss-tool
```

2. **安装依赖**
```bash
# 使用国内镜像源（推荐）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用默认源
pip install -r requirements.txt
```

3. **启动应用**
```bash
python app.py
```

4. **访问界面**
```
http://localhost:5000
```

## 🏗️ 项目架构

```
video-to-rss-tool/
├── app.py                    # Flask主应用入口
├── config.py                 # 全局配置管理
├── requirements.txt          # 项目依赖
├── start.bat                # Windows一键启动脚本
├── utils/                   # 核心工具模块
│   ├── bilibili_api.py      # B站API封装（WBI加密处理）
│   ├── video_downloader.py  # 视频下载器（智能模式切换）
│   ├── video_parser.py      # 视频解析器（向下兼容）
│   ├── rss_generator.py     # RSS生成器
│   ├── audio_proxy.py       # 音频代理服务
│   ├── video_proxy.py       # 视频代理服务
│   └── downloaders/         # 下载器模块
│       ├── base.py          # 基础下载器
│       ├── bilibili_downloader.py  # B站专用下载器
│       └── factory.py       # 下载器工厂
├── templates/               # Web界面模板
│   ├── index.html          # 主页面
│   ├── config.html         # 配置页面
│   └── player.html         # 播放器页面
├── docs/                   # 技术文档
│   ├── B站视频解析技术实现总结.md
│   └── 项目结构优化建议.md
└── cache/                  # 缓存目录
    ├── audio/              # 音频缓存
    └── video/              # 视频缓存
```

## ⚡ 性能优化详解

### 🎯 Bilibili解析优化

我们针对B站视频解析进行了深度优化，实现了**2小时视频2.2秒解析**的突破性性能：

#### 核心优化策略：

1. **智能API选择**
   ```python
   # 快速模式：优先使用bilibili_api
   if fast_mode and 'bilibili.com' in url:
       return self._extract_with_bilibili_api(url)
   # 完整模式：回退到yt-dlp
   else:
       return self._extract_with_ytdlp(url)
   ```

2. **WBI加密缓存**
   ```python
   # 10分钟密钥缓存，避免重复获取
   if time.time() - self.wbi_cache_time < 600:
       return self.cached_wbi_keys
   ```

3. **会话级超时设置**
   ```python
   # 精确的超时控制
   session.timeout = (3, 8)  # 3秒连接，8秒读取
   ```

4. **DASH分片过滤**
   ```python
   # 智能过滤不可播放的分片链接
   def _is_dash_segment(url):
       return (url.endswith('.m4s') or 
               'playurlv3' in url or 
               'mcdn.bilivideo.cn' in url)
   ```

### 📊 性能对比

| 解析方式 | 2小时视频解析时间 | 成功率 | 链接质量 |
|---------|------------------|--------|----------|
| **优化后** | **2.2秒** | 95%+ | 直接MP4链接 |
| 优化前 | 超时(>60秒) | 60% | DASH分片 |
| SnapAny插件 | ~2秒 | 90% | 直接链接 |

## 🔧 高级配置

### Bilibili视频支持

本工具支持多种方式访问B站视频：

#### 方式一：免登录模式（默认）
- 使用基础Cookie和WBI加密
- 支持大部分公开视频
- 无需用户登录

#### 方式二：Cookie导入模式
```bash
# 从浏览器导出Cookie（可选）
yt-dlp https://www.bilibili.com --cookies-from-browser chrome --dump-cookies bilibili_cookies.txt
```

### 配置文件说明

主要配置项位于 `config.py`：

```python
# 支持的平台
SUPPORTED_PLATFORMS = ['youtube', 'bilibili', 'generic']

# 超时设置
CONNECT_TIMEOUT = 3  # 连接超时
READ_TIMEOUT = 8     # 读取超时

# 缓存设置
WBI_CACHE_DURATION = 600  # WBI密钥缓存时间（秒）
```

## 🚀 使用示例

### 基本用法

1. **启动服务**
   ```bash
   python app.py
   ```

2. **访问Web界面**
   - 打开浏览器访问 `http://localhost:5000`
   - 输入视频URL（支持B站、YouTube等）
   - 点击"解析"按钮

3. **获取RSS链接**
   - 解析成功后会显示RSS订阅链接
   - 可直接在播客应用中订阅
   - 支持AI转写工具导入

### API调用

```python
# 直接调用解析接口
import requests

response = requests.post('http://localhost:5000/parse', {
    'url': 'https://www.bilibili.com/video/BV1yNH7zbE8v/',
    'fast_mode': True  # 启用快速模式
})

rss_data = response.text
```

## 🛠️ 开发指南

### 本地开发

1. **克隆项目**
   ```bash
   git clone https://github.com/yourusername/video-to-rss-tool.git
   cd video-to-rss-tool
   ```

2. **创建虚拟环境**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 或
   venv\Scripts\activate     # Windows
   ```

3. **安装开发依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **启动开发服务器**
   ```bash
   python app.py
   ```

### 添加新平台支持

1. 在 `utils/downloaders/` 目录下创建新的下载器
2. 继承 `BaseDownloader` 类
3. 实现 `extract_info` 方法
4. 在 `factory.py` 中注册新下载器

## 📚 技术文档

- [B站视频解析技术实现总结](docs/B站视频解析技术实现总结.md)
- [项目结构优化建议](docs/项目结构优化建议.md)

## 🙏 致谢

本项目在开发过程中参考了以下优秀的开源项目：

- **[BiliNote](https://github.com/JefferyHcool/BiliNote)** - B站视频笔记和转写工具
- **[BilibiliDown](https://github.com/nICEnnnnnnnLee/BilibiliDown)** - B站视频下载工具  
- **[MediaGo](https://github.com/caorushizi/mediago)** - 媒体资源管理工具
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - 强大的视频下载工具

感谢这些项目的开发者们的贡献！

## 🤝 贡献指南

欢迎提交Pull Request或Issue来改进项目！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🔗 相关链接

- [项目主页](https://github.com/yourusername/video-to-rss-tool)
- [问题反馈](https://github.com/yourusername/video-to-rss-tool/issues)
- [更新日志](https://github.com/yourusername/video-to-rss-tool/releases)

---

**⭐ 如果这个项目对你有帮助，请给个Star支持一下！**