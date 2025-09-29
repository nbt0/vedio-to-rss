# 视频转RSS工具

一个将视频网站内容转换为RSS订阅源的工具，支持YouTube、Bilibili等平台，便于在播客应用或AI转写工具中使用。

## 功能特点

- 支持多平台视频解析（YouTube、Bilibili等）
- 自动提取视频/音频直链，生成标准RSS订阅源
- 内置代理支持，解决API访问限制问题
- 友好的Web界面，便于配置和管理
- 支持音频缓存，减少重复下载

## 安装使用

### 环境要求

- Python 3.8+
- 依赖库：Flask, yt-dlp, requests等

### 一键安装（推荐）

Windows系统下，可以使用以下命令一键安装并启动：

```bash
# 下载并安装
git clone https://github.com/yourusername/video-to-rss-tool.git && cd video-to-rss-tool && start.bat
```

或者使用PowerShell：

```powershell
# PowerShell一键安装
git clone https://github.com/yourusername/video-to-rss-tool.git; cd video-to-rss-tool; .\start.bat
```

### 使用国内镜像安装（解决依赖下载慢的问题）

如果您在中国大陆地区，可以使用以下命令通过镜像源安装依赖：

```bash
# 使用清华镜像源安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

或者在start.bat中添加镜像源参数（已内置）：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 手动安装步骤

1. 克隆仓库
```bash
git clone https://github.com/yourusername/video-to-rss-tool.git
cd video-to-rss-tool
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 运行应用
```bash
python app.py
```
或使用Windows批处理文件
```
start.bat
```

4. 访问Web界面
```
http://localhost:5000
```

### Bilibili视频支持

本工具支持两种方式获取Bilibili视频：

#### 方式一：扫码登录（推荐）

首次使用时，程序会自动弹出扫码登录界面，扫码后将自动保存Cookie到本地文件。

#### 方式二：手动导入Cookie

1. 准备Bilibili cookies文件（Netscape格式）
```bash
# 使用yt-dlp从浏览器导出cookies
yt-dlp https://www.bilibili.com --cookies-from-browser chrome --dump-cookies bilibili_cookies.txt
```

2. 将cookies文件放在项目根目录

## 已知问题

- 解析速度较慢，特别是对于大型视频
- 分P视频可能导致解析超时，生成失败

## 技术架构

- 前端：HTML/CSS/JavaScript
- 后端：Flask (Python)
- 视频解析：yt-dlp + 自定义Bilibili API
- RSS生成：自定义XML生成器

## 参考项目

本项目在开发过程中参考了以下优秀的开源项目：

1. **BiliNote** - B站视频笔记和转写工具
   - 项目地址：[BiliNote](https://github.com/JefferyHcool/BiliNote)
   - 参考内容：B站API调用方式和视频处理流程

2. **BilibiliDown** - B站视频下载工具
   - 项目地址：[BilibiliDown](https://github.com/nICEnnnnnnnLee/BilibiliDown)
   - 参考内容：B站视频解析技术和音频提取方法

3. **MediaGo** - 媒体资源管理工具
   - 项目地址：[MediaGo](https://github.com/caorushizi/mediago)
   - 参考内容：Web界面设计和用户体验优化

感谢这些项目的开发者们的贡献！本项目遵循各开源项目的许可协议。

## 贡献指南

欢迎提交Pull Request或Issue来改进项目。

## 许可证

MIT License