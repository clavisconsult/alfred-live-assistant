import os

import threading

from memory_manager import MemoryManager

memory_manager = MemoryManager()



# Preload heavy modules in background to eliminate import blocking

def _preload_heavy():

    try:

        import google.genai

        from google.genai import types

        import pycaw

    except: pass

threading.Thread(target=_preload_heavy, daemon=True).start()



# Global App Cache for O(1) Instant Application Launching

global_app_cache = {}

def _build_app_cache():

    bad_words = ["uninstall", "readme", "help", "setup", "install", "url", "website", "reset", "safe mode", "config"]

    paths = [

        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),

        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",

        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),

        r"C:\Users\Public\Desktop"

    ]

    for p in paths:

        if os.path.exists(p):

            for root, dirs, files in os.walk(p):

                for f in files:

                    fl = f.lower()

                    if fl.endswith(".lnk") and not any(bw in fl for bw in bad_words):

                        # Store by exact lowercase name without .lnk

                        name_key = fl.replace(".lnk", "")

                        if name_key not in global_app_cache:

                            global_app_cache[name_key] = os.path.join(root, f)



threading.Thread(target=_build_app_cache, daemon=True).start()



import sys



import os







# Redirect standard streams to prevent pythonw.exe from crashing on Warnings



sys.stdout = open(os.devnull, "w")



sys.stderr = open(os.devnull, "w")







import asyncio



import traceback



import pyaudio



import threading



import queue



import subprocess



import json



import numpy as np



import http.server



import socketserver



import time



from dotenv import load_dotenv







# Load API Key securely from .env



load_dotenv()







import ctypes



kernel32 = ctypes.windll.kernel32



_alfred_mutex = kernel32.CreateMutexW(None, True, "AlfredAssistantRunningMutex")



if kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS



    sys.exit(0) # Prevent multiple GUI instances natively











from PyQt6.QtWidgets import (



    QApplication, QMainWindow, QWidget, QVBoxLayout, 



    QMenu



)



from PyQt6.QtCore import Qt, pyqtSignal, QObject, QUrl, QTimer, QPoint



from PyQt6.QtWebEngineWidgets import QWebEngineView



from PyQt6.QtWebEngineCore import QWebEngineSettings



from PyQt6.QtGui import QAction















FORMAT = pyaudio.paInt16



CHANNELS = 1



INPUT_RATE = 16000



OUTPUT_RATE = 24000



CHUNK = 1024







WEB_DIR = os.path.dirname(os.path.abspath(__file__))







def get_fft_bins(data, num_bins=32):



    if not data: return [0.0] * num_bins



    audio_data = np.frombuffer(data, dtype=np.int16)



    



    if np.max(np.abs(audio_data)) < 150:



        return [0.0] * num_bins



        



    fft_complex = np.fft.rfft(audio_data)



    fft_mag = np.abs(fft_complex)



    



    usable_bins = fft_mag[:512]



    chunk_size = len(usable_bins) // num_bins



    if chunk_size == 0: return [0.0] * num_bins



        



    binned = []



    for i in range(num_bins):



        chunk = usable_bins[i*chunk_size : (i+1)*chunk_size]



        avg = np.mean(chunk) if len(chunk) > 0 else 0



        



        if avg > 1:



            val = (np.log10(avg) - 2.5) / 3.5



        else:



            val = 0.0



            



        val = max(0.0, min(1.0, val))



        if i < 5: 



            val = min(1.0, val * 1.5)



            



        binned.append(float(val))



    return binned







class WorkerSignals(QObject):



    log = pyqtSignal(str)



    fft_data = pyqtSignal(list)



    finished = pyqtSignal()







class DragOverlay(QWidget):



    def __init__(self, parent=None):



        super().__init__(parent)



        self.parent_window = parent



        self.drag_pos = None







    def mousePressEvent(self, event):



        if event.button() == Qt.MouseButton.LeftButton:



            self.drag_pos = event.globalPosition().toPoint()



        elif event.button() == Qt.MouseButton.RightButton:



            menu = QMenu(self)



            



            mute_action = QAction("Unmute Microphone" if self.parent_window.mic_muted else "Mute Microphone", self)



            mute_action.triggered.connect(self.parent_window.toggle_mute)



            menu.addAction(mute_action)



            



            mic_menu = menu.addMenu("Select Microphone")



            temp_p = pyaudio.PyAudio()



            for i in range(temp_p.get_device_count()):



                info = temp_p.get_device_info_by_index(i)



                if info["maxInputChannels"] > 0:



                    action = QAction(info["name"], self)



                    action.triggered.connect(lambda checked, idx=i: self.parent_window.set_mic_index(idx))



                    mic_menu.addAction(action)



            temp_p.terminate()



            



            exit_action = QAction("Shutdown Alfred", self)



            exit_action.triggered.connect(self.parent_window.close_app)



            menu.addAction(exit_action)



            



            menu.exec(event.globalPosition().toPoint())







    def mouseDoubleClickEvent(self, event):



        if event.button() == Qt.MouseButton.LeftButton:



            self.parent_window.toggle_mute()







    def mouseMoveEvent(self, event):



        if self.drag_pos is not None:



            delta = event.globalPosition().toPoint() - self.drag_pos



            self.parent_window.move(self.parent_window.pos() + delta)



            self.drag_pos = event.globalPosition().toPoint()







    def mouseReleaseEvent(self, event):



        self.drag_pos = None







class AlfredApp(QMainWindow):



    def __init__(self):



        super().__init__()



        self.setWindowTitle("Alfred - Intelligent Assistant")



        self.resize(350, 350)



        self.mic_muted = False



        



        # Make the window a floating widget (frameless, stays on top, transparent background)



        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)



        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)







        # Optimization: Spawn widget in the bottom-right corner (above taskbar)



        screen = QApplication.primaryScreen().availableGeometry()



        self.move(screen.width() - 350 - 20, screen.height() - 350 - 20)







        central_widget = QWidget(self)



        central_widget.setStyleSheet("background: transparent;")



        self.setCentralWidget(central_widget)



        



        # We use absolute positioning so the overlay sits exactly on top of the webview



        self.web_view = QWebEngineView(central_widget)



        self.web_view.setGeometry(0, 0, 350, 350)



        self.web_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)



        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)



        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)



        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)



        html_path = os.path.join(WEB_DIR, "jarvis_hud.html")



        self.web_view.setUrl(QUrl.fromLocalFile(html_path))







        self.overlay = DragOverlay(self)



        self.overlay.setGeometry(0, 0, 350, 350)



        self.overlay.setStyleSheet("background: transparent;")







        # Threading/State



        self.signals = WorkerSignals()



        self.signals.fft_data.connect(self.update_hud)



        self.signals.finished.connect(self.on_session_ended)



        



        self.cancel_event = threading.Event()



        self.pending_exit = False



        self.exit_requested = False



        self.turn_completed_after_exit = False



        self.alfred_is_speaking = False



        self.speaker_cooldown = 0



        self.audio_out_queue = queue.Queue()



        self.loop_thread = None



        self.playback_thread = None



        self.mic_thread = None







        # Automatically start listening immediately



        QTimer.singleShot(0, self.start_assistant)







    def resizeEvent(self, event):



        super().resizeEvent(event)



        self.web_view.setGeometry(0, 0, self.width(), self.height())



        self.overlay.setGeometry(0, 0, self.width(), self.height())







    def update_hud(self, fft_array):



        json_data = json.dumps(fft_array)



        self.web_view.page().runJavaScript(f"if(typeof window.updateAudioData === 'function') window.updateAudioData({json_data});")







    def start_assistant(self):



        self.cancel_event.clear()



        while not self.audio_out_queue.empty():



            try: self.audio_out_queue.get_nowait()



            except queue.Empty: break



            



        self.loop_thread = threading.Thread(target=self.run_asyncio, daemon=True)



        self.loop_thread.start()







    def close_app(self):



        self.cancel_event.set()



        QApplication.quit()







    def on_session_ended(self):



        self.update_hud([0.0] * 32)



        # Attempt to reconnect if dropped



        if not self.cancel_event.is_set():



            QTimer.singleShot(3000, self.start_assistant)



        else:



            self.close()



            QApplication.quit()







    def toggle_mute(self):



        self.mic_muted = not self.mic_muted



        js_bool = "true" if self.mic_muted else "false"



        self.web_view.page().runJavaScript(f"if(typeof window.setMuteState === 'function') window.setMuteState({js_bool});")







    def set_mic_index(self, index):



        with open("mic_config.json", "w") as f:



            json.dump({"mic_index": index}, f)



        # Seamlessly restart the AI session without closing the UI



        self.cancel_event.set()



        QTimer.singleShot(1000, self.start_assistant)







    def run_asyncio(self):



        if sys.platform == 'win32':



            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())



        loop = asyncio.new_event_loop()



        asyncio.set_event_loop(loop)



        try:



            loop.run_until_complete(self.main_async(loop))



        except Exception as e:



            with open("gui_error.log", "a") as f:



                f.write(f"Run asyncio error: {e}\n{traceback.format_exc()}\n")



        finally:
            self.cancel_event.set()
            if stream_in:
                try: stream_in.stop_stream(); stream_in.close()
                except: pass
            if stream_out:
                try: stream_out.stop_stream(); stream_out.close()
                except: pass
            if p:
                try: p.terminate()
                except: pass






from PyQt6.QtGui import QIcon







if __name__ == "__main__":



    app = QApplication(sys.argv)



    



    # Set the global application icon for the taskbar



    icon_path = os.path.join(WEB_DIR, "alfred.ico")



    if os.path.exists(icon_path):



        app.setWindowIcon(QIcon(icon_path))



        



    window = AlfredApp()



    window.showNormal() # Force standard visibility



    window.raise_()     # Bring to front



    window.activateWindow() # Request focus



    sys.exit(app.exec())



