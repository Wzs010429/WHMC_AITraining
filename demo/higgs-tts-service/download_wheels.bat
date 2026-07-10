@echo off
REM ============================================================
REM 下载全部依赖到 wheels/ 文件夹（离线安装包）
REM 在你自己的 Windows 电脑上运行（需要联网）
REM ============================================================
echo.
echo === 下载 Higgs TTS 全部依赖包 ===
echo.

REM 创建临时 venv（不影响现有环境）
if not exist _tmp_env (
    python -m venv _tmp_env
)
call _tmp_env\Scripts\activate

REM 升级 pip
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

REM 创建 wheels 目录
if not exist wheels mkdir wheels

REM 下载 requirements.txt 中的包及其所有依赖
echo.
echo [1/2] 下载 Python 依赖...
pip download -r requirements.txt -d wheels -i https://pypi.tuna.tsinghua.edu.cn/simple

REM 下载 PyTorch（CUDA 12.4 版，~2.5GB）
echo.
echo [2/2] 下载 PyTorch（较大，耐心等待）...
pip download torch==2.5.1 torchaudio==2.5.1 -d wheels --index-url https://download.pytorch.org/whl/cu124

REM 清理临时环境
call deactivate
rmdir /s /q _tmp_env

echo.
echo === 完成！wheels/ 文件夹已生成 ===
echo 大小：
dir wheels /s
echo.
echo 将该 wheels/ 文件夹和代码一起拷贝给学生
pause
