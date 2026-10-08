import os
import sys
import json
import subprocess
import time
import psutil
import vosk
import pyaudio
import numpy as np

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

tray_icon = QSystemTrayIcon(QIcon(os.path.join(os.path.dirname(__file__), "alfred.ico")), app)
tray_menu = QMenu()

def set_mic_index(index):
    with open("mic_config.json", "w") as f:
        json.dump({"mic_index": index}, f)
    # The stream will be re-created automatically in the loop if we set it to None, 
    # but we need a way to communicate this to the listen_loop thread.
    # A simple file touch or global variable works.
    global force_mic_reload
    force_mic_reload = True

force_mic_reload = False
mic_menu = tray_menu.addMenu("Microphone")
temp_p = pyaudio.PyAudio()
for i in range(temp_p.get_device_count()):
    info = temp_p.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0:
        action = QAction(info["name"], app)
        action.triggered.connect(lambda checked, idx=i: set_mic_index(idx))
        mic_menu.addAction(action)
temp_p.terminate()

quit_action = QAction("Quit Alfred Background Engine")
quit_action.triggered.connect(lambda: sys.exit(0))
tray_menu.addAction(quit_action)
tray_icon.setContextMenu(tray_menu)
tray_icon.setToolTip("Alfred is listening...")
tray_icon.show()


MODEL_DIR = os.path.join(os.path.dirname(__file__), "vosk_model")
ALFRED_APP_PATH = os.path.join(os.path.dirname(__file__), "main_gui.py")

vosk.SetLogLevel(-1)

try:
    model = vosk.Model(MODEL_DIR)
except Exception as e:
    with open("fatal_crash.log", "a") as f:
        f.write(f"Model failed: {e}\n")
    sys.exit(1)

grammar = '["alfred", "hey alfred", "wake up alfred", "hello alfred", "[unk]"]'
recognizer = vosk.KaldiRecognizer(model, 16000, grammar)



import ctypes

def is_alfred_running():
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.OpenMutexW(0x00100000, False, "AlfredAssistantRunningMutex")
    if mutex:
        kernel32.CloseHandle(mutex)
        return True
    return False

def launch_alfred():
    if not is_alfred_running():
        # Mirror exactly what happens when the user double clicks the desktop icon
        shortcut_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "Alfred.lnk")
        if os.path.exists(shortcut_path):
            os.startfile(shortcut_path)
        else:
            subprocess.Popen([sys.executable.replace("python.exe", "pythonw.exe"), ALFRED_APP_PATH], cwd=os.path.dirname(__file__))

def get_saved_mic_index():
    try:
        with open("mic_config.json", "r") as f:
            return json.load(f).get("mic_index", None)
    except: return None

def listen_loop():
    global force_mic_reload
    p = pyaudio.PyAudio()
    stream = None
    
    while True:
        app.processEvents()
        try:
            if force_mic_reload:
                force_mic_reload = False
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
                    stream = None
            
            if is_alfred_running():
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
                    stream = None
                time.sleep(2)
                continue
                
            if stream is None:
                idx = get_saved_mic_index()
                try:
                    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4000, input_device_index=idx)
                    stream.start_stream()
                except Exception as e:
                    # Fallback to default
                    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4000)
                    stream.start_stream()
                
            data = stream.read(4000, exception_on_overflow=False)
            
            if recognizer.AcceptWaveform(data):
                res = json.loads(recognizer.Result())
                text = res.get("text", "")
                
                if text.strip():
                    with open("wake_debug.log", "a") as f:
                        f.write(f"Vosk heard: {text}\n")
                        
                if "alfred" in text.lower():
                    if stream is not None:
                        stream.stop_stream()
                        stream.close()
                        stream = None
                    launch_alfred()
                    time.sleep(5)
        except Exception as e:
            with open("fatal_crash.log", "a") as f:
                f.write(f"Loop caught exception: {e}\n")
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass
                stream = None
            time.sleep(1)

if __name__ == "__main__":
    try:
        listen_loop()
    except Exception as e:
        with open("fatal_crash.log", "a") as f:
            f.write(f"Loop crashed: {e}\n")
        sys.exit(1)
