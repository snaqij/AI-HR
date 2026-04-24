@echo off
REM Batch generate interview invitations for multiple resumes

echo ==========================================
echo Batch Interview Invitation Generation
echo ==========================================

set API_BASE=http://127.0.0.1:8000/api/v1
set FRONTEND_BASE=http://localhost:5173

set total=8
set success=0
set failed=0

REM Resume 1: Java后端
echo.
echo [1/%total%] Processing: data/测试文本简历
echo ----------------------------------------
if exist "data\测试文本简历" (
    python scripts\generate_interview_invite.py --api-base %API_BASE% --frontend-base %FRONTEND_BASE% --resume "data\测试文本简历" --no-send-email
    if %errorlevel% equ 0 (
        echo SUCCESS
        set /a success+=1
    ) else (
        echo FAILED
        set /a failed+=1
    )
    timeout /t 2 /nobreak >nul
) else (
    echo SKIP: Resume file not found
    set /a failed+=1
)

REM Resume 2: 前端
echo.
echo [2/%total%] Processing: data/测试文本简历-前端
echo ----------------------------------------
if exist "data\测试文本简历-前端" (
    python scripts\generate_interview_invite.py --api-base %API_BASE% --frontend-base %FRONTEND_BASE% --resume "data\测试文本简历-前端" --no-send-email
    if %errorlevel% equ 0 (
        echo SUCCESS
        set /a success+=1
    ) else (
        echo FAILED
        set /a failed+=1
    )
    timeout /t 2 /nobreak >nul
) else (
    echo SKIP: Resume file not found
    set /a failed+=1
)

REM Resume 3: 全栈
echo.
echo [3/%total%] Processing: data/resume_fullstack.txt
echo ----------------------------------------
if exist "data\resume_fullstack.txt" (
    python scripts\generate_interview_invite.py --api-base %API_BASE% --frontend-base %FRONTEND_BASE% --resume "data\resume_fullstack.txt" --no-send-email
    if %errorlevel% equ 0 (
        echo SUCCESS
        set /a success+=1
    ) else (
        echo FAILED
        set /a failed+=1
    )
    timeout /t 2 /nobreak >nul
) else (
    echo SKIP: Resume file not found
    set /a failed+=1
)

REM Resume 4: 产品经理
echo.
echo [4/%total%] Processing: data/resume_product_manager.txt
echo ----------------------------------------
if exist "data\resume_product_manager.txt" (
    python scripts\generate_interview_invite.py --api-base %API_BASE% --frontend-base %FRONTEND_BASE% --resume "data\resume_product_manager.txt" --no-send-email
    if %errorlevel% equ 0 (
        echo SUCCESS
        set /a success+=1
    ) else (
        echo FAILED
        set /a failed+=1
    )
    timeout /t 2 /nobreak >nul
) else (
    echo SKIP: Resume file not found
    set /a failed+=1
)

REM Resume 5: UI设计师
echo.
echo [5/%total%] Processing: data/resume_ui_designer.txt
echo ----------------------------------------
if exist "data\resume_ui_designer.txt" (
    python scripts\generate_interview_invite.py --api-base %API_BASE% --frontend-base %FRONTEND_BASE% --resume "data\resume_ui_designer.txt" --no-send-email
    if %errorlevel% equ 0 (
        echo SUCCESS
        set /a success+=1
    ) else (
        echo FAILED
        set /a failed+=1
    )
    timeout /t 2 /nobreak >nul
) else (
    echo SKIP: Resume file not found
    set /a failed+=1
)

REM Resume 6: 数据分析师
echo.
echo [6/%total%] Processing: data/resume_data_analyst.txt
echo ----------------------------------------
if exist "data\resume_data_analyst.txt" (
    python scripts\generate_interview_invite.py --api-base %API_BASE% --frontend-base %FRONTEND_BASE% --resume "data\resume_data_analyst.txt" --no-send-email
    if %errorlevel% equ 0 (
        echo SUCCESS
        set /a success+=1
    ) else (
        echo FAILED
        set /a failed+=1
    )
    timeout /t 2 /nobreak >nul
) else (
    echo SKIP: Resume file not found
    set /a failed+=1
)

REM Resume 7: DevOps
echo.
echo [7/%total%] Processing: data/resume_devops.txt
echo ----------------------------------------
if exist "data\resume_devops.txt" (
    python scripts\generate_interview_invite.py --api-base %API_BASE% --frontend-base %FRONTEND_BASE% --resume "data\resume_devops.txt" --no-send-email
    if %errorlevel% equ 0 (
        echo SUCCESS
        set /a success+=1
    ) else (
        echo FAILED
        set /a failed+=1
    )
    timeout /t 2 /nobreak >nul
) else (
    echo SKIP: Resume file not found
    set /a failed+=1
)

REM Resume 8: 公务员
echo.
echo [8/%total%] Processing: data/resume_civil_servant.txt
echo ----------------------------------------
if exist "data\resume_civil_servant.txt" (
    python scripts\generate_interview_invite.py --api-base %API_BASE% --frontend-base %FRONTEND_BASE% --resume "data\resume_civil_servant.txt" --no-send-email
    if %errorlevel% equ 0 (
        echo SUCCESS
        set /a success+=1
    ) else (
        echo FAILED
        set /a failed+=1
    )
) else (
    echo SKIP: Resume file not found
    set /a failed+=1
)

echo.
echo ==========================================
echo Batch Generation Summary
echo ==========================================
echo Total: %total%
echo Success: %success%
echo Failed: %failed%
echo ==========================================

pause
