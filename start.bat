@echo off
chcp 65001 >nul
echo ========================================
echo 视频转RSS工具 - 启动脚本
echo ========================================
echo.

:: 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python，请先安装Python 3.7+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [信息] Python环境检查通过

:: 检查是否存在虚拟环境
if not exist "venv" (
    echo [信息] 创建虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [成功] 虚拟环境创建完成
)

:: 激活虚拟环境
echo [信息] 激活虚拟环境...
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [错误] 虚拟环境激活失败
    pause
    exit /b 1
)

:: 检查依赖是否安装
echo [信息] 检查依赖包...
pip show flask >nul 2>&1
if %errorlevel% neq 0 (
    echo [信息] 安装依赖包...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [错误] 依赖包安装失败
        pause
        exit /b 1
    )
    echo [成功] 依赖包安装完成
) else (
    echo [信息] 依赖包已安装
)

:: 检查yt-dlp是否为最新版本
echo [信息] 更新yt-dlp到最新版本...
pip install --upgrade yt-dlp

:: 创建必要的目录
if not exist "logs" mkdir logs
if not exist "cache" mkdir cache
if not exist "static" mkdir static

echo.
echo ========================================
echo 启动视频转RSS工具
echo ========================================
echo.
echo [信息] 服务将在以下地址启动:
echo [信息] 本地访问: http://localhost:5000
echo [信息] 网络访问: http://0.0.0.0:5000
echo.
echo [提示] 按 Ctrl+C 可停止服务
echo [提示] 关闭此窗口也会停止服务
echo.

:: 启动Flask应用
python app.py

:: 如果程序异常退出，显示错误信息
if %errorlevel% neq 0 (
    echo.
    echo [错误] 应用启动失败，错误代码: %errorlevel%
    echo [建议] 请检查:
    echo   1. Python环境是否正确
    echo   2. 依赖包是否完整安装
    echo   3. 端口5000是否被占用
    echo   4. 查看logs文件夹中的日志文件
    echo.
)

echo.
echo 按任意键退出...
pause >nul