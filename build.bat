@echo off
setlocal enabledelayedexpansion

set HERE=%~dp0
set WORK=%TEMP%\engine
set MSYS=C:\msys64\ucrt64\bin

cd /d %HERE%

echo ============================================================
echo  build.bat - Cyfamate / Pyfamate / Zyfamate
echo    usage: build.bat [force]   ^(force = delete exes and rebuild^)
echo    env overrides: CXX ^(C++ compiler^), ZCC ^(C compiler^),
echo                   PYFAMATE_PYTHON ^(python.exe path^)
echo                   PYFAMATE_TORCH=1 ^(旧torch同梱^)
echo    既定: 外部依存は fontTools 含め全非同梱 ^(実行時に自動解決^)。
echo          pip は一切実行しない ^(実行時ノブに一元化^)
echo    Existing tools in PATH are always preferred; nothing is
echo    downloaded or installed unless no usable tool is found.
echo ============================================================
echo.

if /i "%~1"=="force" (
    echo [FORCE] rebuilding all ...
    del /q "%HERE%Cyfamate.exe" "%HERE%pyfamate.exe" "%HERE%Zyfamate.exe" 2>nul
)

set FAIL=0
REM suppress pip's version-check notices
set PIP_DISABLE_PIP_VERSION_CHECK=1
REM MSYS2 (if present) is APPENDED to PATH so user-installed tools win.
if exist "%MSYS%" set "PATH=%PATH%;%MSYS%"

REM --- 1. Cyfamate (C++ amalgamation -> Cyfamate.exe) ---
echo [1/3] Cyfamate ...
if exist "%HERE%Cyfamate.exe" (
    echo [SKIP] Cyfamate.exe already exists
    goto pyfamate
)
if not exist cyfamate.cpp (
    echo [SKIP] cyfamate.cpp not found
    goto pyfamate
)
if not defined CXX (
    where /q clang++ 2>nul && set "CXX=clang++"
)
if not defined CXX (
    where /q g++ 2>nul && set "CXX=g++"
)
REM Common MinGW-family install dirs (TDM-GCC, mingw64, w64devkit, scoop)
if not defined CXX for %%D in ("C:\TDM-GCC-64\bin" "C:\mingw64\bin" "C:\w64devkit\bin" "%USERPROFILE%\scoop\shims") do (
    if not defined CXX if exist "%%~D\clang++.exe" set "CXX=%%~D\clang++.exe"
    if not defined CXX if exist "%%~D\g++.exe" set "CXX=%%~D\g++.exe"
)
REM Last resort: install MSYS2 + clang
if not defined CXX (
    echo   no C++ compiler found. Installing MSYS2 clang as last resort ...
    call :ensure_msys
    if errorlevel 1 ( set FAIL=1 & goto pyfamate )
    C:\msys64\usr\bin\pacman.exe -S --noconfirm --needed mingw-w64-ucrt-x86_64-clang
    if exist "%MSYS%\clang++.exe" ( set "CXX=%MSYS%\clang++.exe" ) else (
        echo [ERROR] clang++ not found after install
        set FAIL=1
        goto pyfamate
    )
)
set "CXX_EXTRA=-fno-asynchronous-unwind-tables"
echo !CXX! | findstr /i "clang" >nul && set "CXX_EXTRA=-Wno-unused-parameter -fno-threadsafe-statics -fuse-ld=lld"
echo   compiler: !CXX!
"!CXX!" -std=c++17 -O3 -ffast-math -fno-exceptions -fno-rtti ^
    -march=native -flto ^
    -static -Wl,--stack,25000000 -Wl,-s ^
    !CXX_EXTRA! ^
    -lpthread ^
    -o "%HERE%Cyfamate.exe" "%HERE%cyfamate.cpp"
if errorlevel 1 (
    echo [ERROR] Cyfamate build failed
    set FAIL=1
) else (
    echo [OK] Cyfamate.exe
)
echo.

:pyfamate
REM --- 2. Pyfamate (Python -> pyfamate.exe) ---
echo [2/3] Pyfamate ...
if exist "%HERE%pyfamate.exe" (
    echo [SKIP] pyfamate.exe already exists
    goto zyfamate
)
if not exist pyfamate.py (
    echo [SKIP] pyfamate.py not found
    goto zyfamate
)
REM Find a real Python (validated by running it: rejects the MS Store stub)
set "PYCMD="
if defined PYFAMATE_PYTHON if exist "%PYFAMATE_PYTHON%" set "PYCMD=%PYFAMATE_PYTHON%"
if not defined PYCMD python -c "print(1)" >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD py -3 -c "print(1)" >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD (
    echo   no usable Python found. Installing via MSYS2 as last resort ...
    call :ensure_msys
    if errorlevel 1 ( set FAIL=1 & goto zyfamate )
    C:\msys64\usr\bin\pacman.exe -S --noconfirm --needed mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-python-pip
    python -c "print(1)" >nul 2>&1 && set "PYCMD=python"
    if not defined PYCMD (
        echo [ERROR] Python still not usable after install
        set FAIL=1
        goto zyfamate
    )
)
echo   python: !PYCMD!
!PYCMD! -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    REM [NO-PIP 2026-07-08] build.bat は pip を一切実行しない (ユーザー方針)。
    echo [ERROR] PyInstaller がありません。手動で導入してから再実行してください:
    echo          !PYCMD! -m pip install pyinstaller
    set FAIL=1
    goto zyfamate
)
REM [2026-07-08 NO-PIP / NO-BUNDLE-ORT] build.bat はパッケージを導入も削除も
REM しない。さらに onnxruntime は exe に *同梱しない* (--exclude-module):
REM PyInstaller が onnxruntime-gpu の DLL 依存 (cuDNN/cuBLAS 等の CUDA DLL 群)
REM を追いかけて exe が数百 MB〜GB 級に肥大するため。実行時は本体がシステム
REM Python の site-packages から解決し、無ければ自動インストールノブ
REM (PYFAMATE_NO_AUTO_INSTALL) 配下で onnxruntime-gpu を導入する (torch と
REM 同じ既存機構)。model 推論の EP は既定 CUDA のみ。DML/CPU は実行時の
REM 明示ノブ (PYFAMATE_SVINFER_DML=1 / PYFAMATE_SVINFER_CPU=1) 専用で、
REM CUDA 失敗時に黙って落ちるフォールバックではない。CUDA/cuDNN の DLL は
REM 実行時にマシン内を自動探索する ([CUDA-DLL-HUNT])。
REM 手順:
REM   1) model.onnx は learn/teacher の保存時に自動生成される ([AUTO-ONNX]。
REM      既存 checkpoint からの手動再生成は python pyfamate.py export-onnx)
REM   2) model 推論の動作確認は必要時のみ手動で: pyfamate.exe check-model
REM 切り替え:
REM   set PYFAMATE_TORCH=1  … 旧フル同梱 (torch 込み数 GB 級; 通常不要)
REM [Linux メモ] 同じ手法がそのまま使える (CUDA EP):
REM   pip install pyinstaller numpy pillow onnxruntime-gpu   (※手動; build スクリプトは pip しない)
REM   pyinstaller --onefile --console --clean -n pyfamate \
REM       --exclude-module torch --exclude-module torchvision --exclude-module torchaudio \
REM       --exclude-module onnxruntime pyfamate.py
REM   ./pyfamate check-model   ← EP=CUDAExecutionProvider を確認
REM 外部依存は fontTools 含め全て非同梱 (exe は stdlib のみ)。必要なものは実行時に
REM 本体がシステム Python から解決し、無ければ自動インストールする既存機構に一任。
set "PYI_EXCLUDES=--exclude-module torch --exclude-module torchvision --exclude-module torchaudio --exclude-module onnxruntime --exclude-module numpy --exclude-module PIL --exclude-module Pillow --exclude-module psutil --exclude-module fontTools --exclude-module fonttools"
if defined PYFAMATE_TORCH (
    echo   [TORCH] 旧フル同梱ビルド ^(torch 込み。サイズ数 GB 級^)
    set "PYI_EXCLUDES="
    !PYCMD! -c "import torch" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] この Python に torch がありません — exe にも同梱されず model.pt は無効になります。
    )
) else (
    echo   [DEFAULT] 外部依存 全非同梱ビルド ^(実行時に解決/自動インストール^)
)
!PYCMD! -m PyInstaller --onefile --console --clean -n pyfamate --distpath %HERE% --workpath %WORK% --specpath %WORK% ^
    !PYI_EXCLUDES! ^
    pyfamate.py
if errorlevel 1 (
    echo [ERROR] Pyfamate build failed
    set FAIL=1
) else (
    echo [OK] pyfamate.exe
    for %%F in ("%HERE%pyfamate.exe") do echo   size: %%~zF bytes
    REM model 推論 (ソース既定 OFF) の確認が要るときだけ手動で: pyfamate.exe check-model
)
echo.

:zyfamate
REM --- 3. Zyfamate (C -> Zyfamate.exe) ---
echo [3/3] Zyfamate ...
if exist "%HERE%Zyfamate.exe" (
    echo [SKIP] Zyfamate.exe already exists
    goto done
)
if not exist Zyfamate.c (
    echo [SKIP] Zyfamate.c not found
    goto done
)
if not defined ZCC (
    where /q gcc 2>nul && set "ZCC=gcc"
)
if not defined ZCC (
    where /q clang 2>nul && set "ZCC=clang"
)
if not defined ZCC for %%D in ("C:\TDM-GCC-64\bin" "C:\mingw64\bin" "C:\w64devkit\bin" "%USERPROFILE%\scoop\shims") do (
    if not defined ZCC if exist "%%~D\gcc.exe" set "ZCC=%%~D\gcc.exe"
    if not defined ZCC if exist "%%~D\clang.exe" set "ZCC=%%~D\clang.exe"
)
if not defined ZCC (
    echo   no C compiler found. Installing MSYS2 gcc as last resort ...
    call :ensure_msys
    if errorlevel 1 ( set FAIL=1 & goto done )
    C:\msys64\usr\bin\pacman.exe -S --noconfirm --needed mingw-w64-ucrt-x86_64-gcc
    if exist "%MSYS%\gcc.exe" ( set "ZCC=%MSYS%\gcc.exe" ) else (
        echo [ERROR] gcc not found after install
        set FAIL=1
        goto done
    )
)
echo   compiler: !ZCC!
REM -O3/-flto. Hash table sizes are auto-detected from physical RAM at runtime
REM (RAM/16 clamped to 256MB..8GB; override with env var ZYFAMATE_HASH_MB).
REM To distribute the same exe to other PCs, change -march=native to -march=x86-64-v2.
"!ZCC!" -O3 -flto -march=native ^
    -static -static-libgcc -Wl,-s -o "%HERE%Zyfamate.exe" "%HERE%Zyfamate.c" -lpthread
if errorlevel 1 (
    echo [ERROR] Zyfamate build failed
    set FAIL=1
) else (
    echo [OK] Zyfamate.exe
)
echo.

:done
rmdir /s /q %WORK% 2>nul

echo ============================================================
if %FAIL%==1 (
    echo  Build finished with errors.
    pause
    exit /b 1
)
echo  Done: %HERE%
pause
exit /b 0

REM ---- subroutine: install MSYS2 only when actually needed ----
:ensure_msys
if exist "C:\msys64\usr\bin\pacman.exe" (
    set "PATH=%PATH%;%MSYS%"
    exit /b 0
)
echo [SETUP] MSYS2 not found. Downloading installer ...
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/msys2/msys2-installer/releases/download/2024-12-08/msys2-x86_64-20241208.exe' -OutFile '%TEMP%\msys2-installer.exe' }"
if not exist "%TEMP%\msys2-installer.exe" (
    echo [ERROR] Download failed. Install MSYS2 manually from https://www.msys2.org
    exit /b 1
)
echo [SETUP] Installing MSYS2 silently ...
"%TEMP%\msys2-installer.exe" install --root C:\msys64 --confirm-command
if not exist "C:\msys64\usr\bin\pacman.exe" (
    echo [ERROR] MSYS2 install failed. Install manually from https://www.msys2.org
    exit /b 1
)
echo [SETUP] Initializing MSYS2 ...
C:\msys64\usr\bin\bash.exe -lc "pacman -Syu --noconfirm" 2>nul
del /q "%TEMP%\msys2-installer.exe" 2>nul
set "PATH=%PATH%;%MSYS%"
echo [OK] MSYS2 installed
exit /b 0
