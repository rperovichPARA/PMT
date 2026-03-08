@echo off
echo ========================================
echo  PMT Launcher
echo ========================================
cd /d C:\Users\rpero\PMT
git config user.email "rperovich@gmail.com"
git config user.name "rperovichPARA"
echo Stashing local changes...
git stash
echo Fetching and checking out feature branch...
git fetch origin
git checkout claude/add-metrics-refresh-FOVhL
git pull origin claude/add-metrics-refresh-FOVhL
echo Starting PMT API Server...
start "PMT API Server" cmd /k "cd /d C:\Users\rpero\PMT && python api_server.py"
echo Waiting for server to start...
timeout /t 5
echo Starting JavaFX Client...
set JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot
set PATH=%PATH%;%JAVA_HOME%\bin;C:\maven\bin
cd /d C:\Users\rpero\PMT\javafx-client
mvn clean javafx:run > C:\Users\rpero\PMT\javafx-output.log 2>&1
echo.
echo Maven exited with code: %ERRORLEVEL%
echo Full output saved to C:\Users\rpero\PMT\javafx-output.log
type C:\Users\rpero\PMT\javafx-output.log
pause
