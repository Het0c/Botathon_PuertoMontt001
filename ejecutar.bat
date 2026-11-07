@echo off
REM Editar las rutas y hacer doble clic
set CONTRATOS=C:\Botathon\Nac - Base contratos x mes.xlsx
set PLANIF=C:\Botathon\Nac - Planificacion Asistencial x mes.xlsx
set SALIDA=C:\Botathon\salida
python "%~dp0bot_traductor.py" --contratos "%CONTRATOS%" --planificacion "%PLANIF%" --salida "%SALIDA%" --csv
if errorlevel 1 (echo ERROR: revisar %SALIDA%\bot_traductor.log) else (echo OK: %SALIDA%\Planificacion_Input_BluePrism.xlsx)
pause
