@echo off
REM ============================================================
REM 下载全部依赖到 wheels/（多源回退，确保不遗漏）
REM 在你的 Windows 电脑上运行（需联网 + 翻墙）
REM ============================================================
echo.
echo === Higgs TTS 离线包下载 ===
echo.

REM 创建临时 venv
if not exist _tmp_env python -m venv _tmp_env
call _tmp_env\Scripts\activate
python -m pip install --upgrade pip

if not exist wheels mkdir wheels

REM ═══════════════════════════════════════════════════
REM 第1批：PyPI 包（清华镜像优先，失败则回退官方）
REM ═══════════════════════════════════════════════════
echo.
echo [1/3] 下载 PyPI 依赖...

REM 先试清华镜像
pip download -r requirements.txt -d wheels ^
    -i https://pypi.tuna.tsinghua.edu.cn/simple ^
    2>&1

REM 如果 transformers 没下到（版本太新清华没同步），从官方补
echo. & echo 补漏：检查 transformers...
pip download "transformers>=5.5.0" -d wheels ^
    -i https://pypi.org/simple/ ^
    2>&1

REM 把 transformers 的深层依赖也补全
pip download "transformers>=5.5.0" -d wheels ^
    2>&1

REM ═══════════════════════════════════════════════════
REM 第2批：PyTorch（必须从官方索引下载）
REM ═══════════════════════════════════════════════════
echo.
echo [2/3] 下载 PyTorch CUDA 12.4 版（~2.5GB）...

pip download torch==2.5.1 torchaudio==2.5.1 -d wheels ^
    --index-url https://download.pytorch.org/whl/cu124 ^
    2>&1

REM ═══════════════════════════════════════════════════
REM 第3批：补全遗漏（pip 自动解析可能没覆盖的）
REM ═══════════════════════════════════════════════════
echo.
echo [3/3] 补全所有传递依赖...

REM 用 pip freeze 找出所有包，全面下载
pip install --no-index --find-links=wheels -r requirements.txt 2>nul
pip install --no-index --find-links=wheels torch==2.5.1 torchaudio==2.5.1 2>nul

REM 补漏：下载当前环境已装但 wheels 里没有的包
for /f "delims==" %%i in ('pip freeze') do (
    pip download "%%i" -d wheels 2>nul
)

REM 清理临时环境
call deactivate
rmdir /s /q _tmp_env

echo.
echo ═══════════════════════════════════════════════════
echo 完成！wheels/ 文件夹内容：
dir wheels /s | findstr /i "个文件"
echo ═══════════════════════════════════════════════════
echo.
echo 将 wheels/ 和代码一起拷给学生即可离线安装
echo 学生运行：install_offline.bat
pause
