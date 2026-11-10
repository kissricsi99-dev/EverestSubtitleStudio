@echo off
py -3.11 -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name EverestSubtitleStudio --collect-all faster_whisper --collect-all ctranslate2 --collect-all av --collect-all tokenizers main.py
pause
