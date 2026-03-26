@echo off
set /p APP_PID=<app.pid
taskkill /F /PID %APP_PID%
del app.pid
echo App stopped.
pause