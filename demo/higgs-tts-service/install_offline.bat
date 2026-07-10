@echo off
REM ============================================================
REM 离线一键安装（无需联网）
REM 前提：wheels/ 文件夹和代码在同一目录
REM ============================================================
echo.
echo === Higgs TTS 离线安装 ===
echo.

REM 创建虚拟环境
if not exist tts-env (
    echo [1/3] 创建虚拟环境...
    python -m venv tts-env
) else (
    echo [1/3] 虚拟环境已存在，跳过
)

call tts-env\Scripts\activate

REM 升级 pip（离线，不连外网）
python -m pip install --upgrade pip --no-index --find-links=wheels 2>nul

REM 安装所有依赖
echo [2/3] 安装依赖包...
pip install --no-index --find-links=wheels -r requirements.txt
pip install --no-index --find-links=wheels torch==2.5.1 torchaudio==2.5.1

REM 验证
echo [3/3] 验证安装...
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"

echo.
echo === 安装完成！===
echo.
echo 启动服务：
echo   tts-env\Scripts\activate
echo   python server.py --model-path ./models/higgs-audio-v3-tts-4b --host 127.0.0.1 --port 8100
echo.
pause
