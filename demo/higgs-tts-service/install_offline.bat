@echo off
chcp 65001 >nul
REM ============================================================
REM 离线一键安装（无需联网，U盘/共享文件夹即装即用）
REM 前提：wheels/ 和 models/ 在同一目录
REM ============================================================
echo.
echo ========================================
echo  Higgs Audio v3 TTS 离线安装
echo ========================================
echo.

REM 检查 wheels 文件夹
if not exist wheels (
    echo [FAIL] wheels 文件夹不存在！请确认离线包完整
    pause & exit /b 1
)

REM 1. 创建虚拟环境
if not exist tts-env (
    echo [1/4] 创建虚拟环境...
    python -m venv tts-env
) else (
    echo [1/4] 虚拟环境已存在
)
call tts-env\Scripts\activate

REM 2. 安装 PyPI 依赖
echo [2/4] 安装 Python 依赖...
pip install --no-index --find-links=wheels -r requirements.txt 2>&1
if %errorlevel% neq 0 (
    echo [WARN] 部分包可能缺失，尝试逐个安装...
    for %%f in (wheels\*.whl) do pip install "%%f" --no-deps 2>nul
)

REM 3. 安装 PyTorch
echo [3/4] 安装 PyTorch CUDA...
pip install --no-index --find-links=wheels torch==2.5.1 torchaudio==2.5.1 2>&1
if %errorlevel% neq 0 (
    REM 降级尝试：不指定版本，装最新的
    for %%f in (wheels\torch-*.whl) do pip install "%%f" 2>nul
    for %%f in (wheels\torchaudio-*.whl) do pip install "%%f" 2>nul
)

REM 4. 验证
echo [4/4] 验证安装...
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A'); import fastapi; import transformers; print('packages: OK')" 2>&1

if %errorlevel% neq 0 (
    echo [FAIL] 安装验证失败
    pause & exit /b 1
)

echo.
echo ========================================
echo  安装完成！
echo ========================================
echo.
echo  启动服务：
echo    tts-env\Scripts\activate
echo    python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 127.0.0.1 --port 8100
echo.
echo  测试：
echo    python quick_tts.py "你好世界"
echo.
pause
