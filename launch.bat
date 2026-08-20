@echo off
echo ========================================
echo  PMT Launcher
echo ========================================
cd /d C:\Users\rpero\PMT


echo Updating from remote...
git stash
git fetch origin claude/jquants-download-performance-Zepav
git checkout claude/jquants-download-performance-Zepav
git pull origin claude/jquants-download-performance-Zepav

echo Starting PMT API Server...
start "PMT API Server" cmd /k "cd /d C:\Users\rpero\PMT && python api_server.py"

echo Starting JavaFX Client...
set JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot
set PATH=%PATH%;%JAVA_HOME%\bin;C:\maven\bin
cd /d C:\Users\rpero\PMT\javafx-client

REM Skip 'clean' to avoid full recompile — use javafx:run directly
REM Maven will only recompile changed files
mvn javafx:run > C:\Users\rpero\PMT\javafx-output.log 2>&1

echo.
echo Maven exited with code: %ERRORLEVEL%
echo Full output saved to C:\Users\rpero\PMT\javafx-output.log
type C:\Users\rpero\PMT\javafx-output.log
pause
