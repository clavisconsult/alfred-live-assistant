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

            loop.close()

            self.signals.finished.emit()



    def _audio_playback_worker(self, stream_out):

        empty_ticks = 0

        while not self.cancel_event.is_set():

            try:

                data = self.audio_out_queue.get(timeout=0.05)

                empty_ticks = 0

                if stream_out.is_active():

                    audio_array = np.frombuffer(data, dtype=np.int16)

                    peak = np.max(np.abs(audio_array)) if len(audio_array) > 0 else 0

                    if peak > 200:

                        self.alfred_is_speaking = True

                        self.speaker_cooldown = 10  # ~0.6 seconds of hangover

                    else:

                        if getattr(self, 'speaker_cooldown', 0) > 0:

                            self.speaker_cooldown -= 1

                        else:

                            self.alfred_is_speaking = False



                    fft_bins = get_fft_bins(data, 32)

                    self.signals.fft_data.emit(fft_bins)

                    

                    with open("gui_error.log", "a") as debugf:

                        debugf.write("PLAYING AUDIO CHUNK: " + str(len(data)) + "\n")

                        

                    stream_out.write(data)

            except queue.Empty:

                empty_ticks += 1

                self.signals.fft_data.emit([0.0] * 32)

                self.alfred_is_speaking = False

                self.speaker_cooldown = 0

                if getattr(self, 'turn_completed_after_exit', False) and empty_ticks > 20:
                    # 1 second of network silence confirms the goodbye audio has fully played out

                    self.cancel_event.set()

                    break

                continue

            except Exception as e:

                break



    def _mic_worker(self, stream_in, loop, mic_queue):

        while not self.cancel_event.is_set():

            try:

                data = stream_in.read(CHUNK, exception_on_overflow=False)

                if not self.mic_muted:

                    if getattr(self, 'alfred_is_speaking', False):

                        # Smart Echo Cancellation (Interruption enabled)

                        audio_array = np.frombuffer(data, dtype=np.int16)

                        rms = np.sqrt(np.mean(np.square(audio_array.astype(np.float32))))

                        # If the sound is quiet/moderate (speaker bleed), mute it.

                        # If the user speaks loudly (RMS > 2500), let the chunk through so Gemini hears the interruption!

                        if rms < 300: # Lowered threshold to ensure user is heard

                            data = b'\x00' * len(data)

                    loop.call_soon_threadsafe(mic_queue.put_nowait, data)

            except Exception as e:

                break



    async def audio_input_task(self, session, mic_queue):

        from google.genai import types

        try:

            while not self.cancel_event.is_set():

                data = await mic_queue.get()

                if not data or len(data) < CHUNK: 

                    continue # Drop malformed/tiny chunks that could bypass PyAudio blocking

                    

                await session.send_realtime_input(

                    audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")

                )


        except asyncio.CancelledError:

            pass

        except Exception as e:

            with open("gui_error.log", "a") as f:

                f.write(f"audio_input_task error: {e}\n{traceback.format_exc()}\n")

            if "Resource has been exhausted" in str(e) or "quota" in str(e).lower():

                subprocess.Popen(["powershell", "-Command", "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('My A. I. brain has exhausted its API quota. Please try again later.')"], creationflags=subprocess.CREATE_NO_WINDOW)

            self.cancel_event.set()



    async def audio_output_task(self, session):

        from google.genai import types

        import json

        try:

            while not self.cancel_event.is_set():

                async for response in session.receive():

                    if self.cancel_event.is_set(): break

                        

                    content = response.server_content

                    if content:

                        if content.interrupted:

                            with open("gemini_transcript.log", "a") as f:

                                f.write("--- INTERRUPTED ---\n")

                            while not self.audio_out_queue.empty():

                                try: self.audio_out_queue.get_nowait()

                                except queue.Empty: break



                        if content.model_turn:

                            for part in content.model_turn.parts:

                                if part.text:

                                    with open("gemini_transcript.log", "a") as f:

                                        f.write(f"Alfred: {part.text}\n")

                                if part.inline_data:

                                    self.audio_out_queue.put(part.inline_data.data)

                                    

                        if content.turn_complete:
                            if getattr(self, 'exit_requested', False):
                                if not getattr(self, 'pending_exit', False):
                                    self.pending_exit = True
                                else:
                                    self.turn_completed_after_exit = True
                            with open("gemini_transcript.log", "a") as f:

                                f.write("--- TURN COMPLETE ---\n")

                            

                    if response.tool_call:

                        function_responses = []

                        for fc in response.tool_call.function_calls:

                            if fc.name == "execute_command":

                                command = fc.args.get("command", "")

                                try:

                                    result = subprocess.check_output(["powershell", "-Command", command], text=True, stderr=subprocess.STDOUT)

                                    out = {"result": result[:1000]}

                                except Exception as e:

                                    out = {"error": str(e)[:1000]}

                                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=out))

                                

                            elif fc.name == "close_application":
                                app_name = fc.args.get("app_name", "").replace("'", "")
                                cmd = f"Get-Process | Where-Object {{ .ProcessName -match '{app_name}' -or .MainWindowTitle -match '{app_name}' }} | Stop-Process -Force -ErrorAction SilentlyContinue"
                                subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", cmd], creationflags=subprocess.CREATE_NO_WINDOW)
                                function_responses.append(types.FunctionResponse(
                                    id=fc.id, name=fc.name, response={"result": f"Sent command to close {app_name}."}
                                ))
                            elif fc.name == "open_application":

                                app_name = fc.args.get("app_name", "")

                                ps_command = f"""

                                $appName = "{app_name}".ToLower().Trim()

                                

                                # 1. Known Windows aliases and protocols

                                $aliases = @{{

                                    "settings" = "ms-settings:"

                                    "windows settings" = "ms-settings:"

                                    "calculator" = "calc"

                                    "calc" = "calc"

                                    "notepad" = "notepad"

                                    "task manager" = "taskmgr"

                                    "control panel" = "control"

                                    "file explorer" = "explorer"

                                    "explorer" = "explorer"

                                    "command prompt" = "cmd"

                                    "cmd" = "cmd"

                                    "word" = "winword"

                                    "excel" = "excel"

                                    "powerpoint" = "powerpnt"

                                    "browser" = "https://www.google.com"

                                }}

                                

                                if ($aliases.ContainsKey($appName)) {{

                                    Start-Process $aliases[$appName]

                                    Write-Output "Successfully opened $appName"

                                    exit

                                }}

                                

                                # 2. Search for shortcuts

                                $search = "*$appName*.lnk"

                                $paths = @("$env:ProgramData\\Microsoft\\Windows\\Start Menu\\Programs", "$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs", "$env:PUBLIC\\Desktop", "$env:USERPROFILE\\Desktop")

                                $shortcut = Get-ChildItem -Path $paths -Recurse -Filter $search -ErrorAction SilentlyContinue | Select-Object -First 1

                                

                                if ($shortcut) {{

                                    Invoke-Item $shortcut.FullName

                                    Write-Output "Successfully opened $($shortcut.Name)"

                                    exit

                                }}

                                

                                # 3. Fallback to PATH executables

                                try {{

                                    Start-Process "{app_name}" -ErrorAction Stop

                                    Write-Output "Successfully opened {app_name}"

                                }} catch {{

                                    Write-Error "Could not find application: {app_name}. Please check the spelling or ensure it is installed."

                                }}

                                """

                                try:

                                    result = subprocess.check_output(["powershell", "-Command", ps_command], text=True, stderr=subprocess.STDOUT)

                                    out = {"result": result[:1000]}

                                except Exception as e:

                                    out = {"error": str(e)[:1000]}

                                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=out))

                                

                            elif fc.name == "search_web":
                                try:
                                    import warnings
                                    warnings.filterwarnings("ignore")
                                    from duckduckgo_search import DDGS
                                    query = fc.args.get("query", "")
                                    with DDGS() as ddgs:
                                        results = [r for r in ddgs.text(query, max_results=4)]
                                        
                                    if results:
                                        snippets = "\n".join([f"Source: {r.get('title')}\nInfo: {r.get('body')}" for r in results])
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"results": snippets[:2000]}))
                                    else:
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"error": "No search results found."}))
                                except Exception as e:
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"error": str(e)}))

                            elif fc.name == "set_system_volume":
                                try:
                                    from pycaw.pycaw import AudioUtilities
                                    level = int(fc.args.get("level_percent", 50))
                                    level = max(0, min(100, level))
                                    devices = AudioUtilities.GetSpeakers()
                                    devices.EndpointVolume.SetMasterVolumeLevelScalar(level / 100.0, None)
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": f"System volume set to {level}%"}))
                                except Exception as e:
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"error": str(e)}))
                                    
                            elif fc.name == "play_youtube_video":
                                import urllib.request
                                import urllib.parse
                                import re
                                import webbrowser
                                try:
                                    query = fc.args.get("query", "")
                                    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
                                    html = urllib.request.urlopen(url)
                                    video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
                                    if video_ids:
                                        final_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
                                        webbrowser.open(final_url)
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": f"Now playing video at {final_url}"}))
                                    else:
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"error": "No videos found for that query."}))
                                except Exception as e:
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"error": str(e)}))

                            elif fc.name == "open_browser_url":

                                url = fc.args.get("url", "")

                                try:

                                    import webbrowser

                                    webbrowser.open(url)

                                    out = {"result": f"Successfully opened {url} in the default browser."}

                                except Exception as e:

                                    out = {"error": str(e)}

                                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=out))

                                

                            elif fc.name == "read_gmail":
                                import imaplib
                                import email
                                from email.header import decode_header
                                
                                count = fc.args.get("count", 5)
                                gmail_user = os.environ.get("GMAIL_ADDRESS")
                                gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
                                
                                if not gmail_user or not gmail_pass:
                                    resp = "Error: Credentials missing. Tell the user exactly this: 'To read your Gmail, you need to add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to your .env file. The password must be a 16-letter App Password generated from your Google Account Security settings.'"
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"error": resp}))
                                else:
                                    try:
                                        mail = imaplib.IMAP4_SSL("imap.gmail.com")
                                        mail.login(gmail_user, gmail_pass)
                                        mail.select("inbox")
                                        
                                        status, messages = mail.search(None, '(UNSEEN)')
                                        if status == "OK" and messages[0]:
                                            msg_ids = messages[0].split()
                                            latest_msg_ids = msg_ids[-int(count):]
                                            
                                            emails_data = []
                                            for msg_id in latest_msg_ids:
                                                res, msg_data = mail.fetch(msg_id, "(RFC822)")
                                                for response_part in msg_data:
                                                    if isinstance(response_part, tuple):
                                                        msg = email.message_from_bytes(response_part[1])
                                                        
                                                        subject_header = decode_header(msg["Subject"])[0]
                                                        subject = subject_header[0]
                                                        if isinstance(subject, bytes):
                                                            subject = subject.decode(subject_header[1] if subject_header[1] else "utf-8", errors="ignore")
                                                            
                                                        sender_header = decode_header(msg.get("From"))[0]
                                                        sender = sender_header[0]
                                                        if isinstance(sender, bytes):
                                                            sender = sender.decode(sender_header[1] if sender_header[1] else "utf-8", errors="ignore")
                                                        
                                                        body = ""
                                                        if msg.is_multipart():
                                                            for part in msg.walk():
                                                                if part.get_content_type() == "text/plain":
                                                                    try:
                                                                        body = part.get_payload(decode=True).decode(errors="ignore")
                                                                        break
                                                                    except: pass
                                                        else:
                                                            try:
                                                                body = msg.get_payload(decode=True).decode(errors="ignore")
                                                            except: pass
                                                            
                                                        emails_data.append({"From": sender, "Subject": subject, "Snippet": body[:500]})
                                            mail.logout()
                                            function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"emails": emails_data}))
                                        else:
                                            mail.logout()
                                            function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"result": "You have no unread emails in Gmail."}))
                                    except Exception as e:
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"error": f"Failed to read Gmail: {str(e)}"}))

                            elif fc.name == "read_active_browser":
                                import uiautomation as auto
                                import pyautogui
                                import pyperclip
                                
                                browser_win = None
                                try:
                                    for win in auto.GetRootControl().GetChildren():
                                        cname = win.ClassName
                                        if "Chrome_WidgetWin_1" in cname or "MozillaWindowClass" in cname:
                                            if win.Name:
                                                browser_win = win
                                                break
                                except:
                                    pass
                                
                                if not browser_win:
                                    function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"error": "No visible browser window found."}))
                                else:
                                    try:
                                        browser_win.SetFocus()
                                    except:
                                        pass
                                    await asyncio.sleep(0.2)
                                    
                                    old_clip = pyperclip.paste()
                                    
                                    # 1. Try to get URL
                                    pyautogui.hotkey('ctrl', 'l')
                                    await asyncio.sleep(0.1)
                                    pyautogui.hotkey('ctrl', 'c')
                                    await asyncio.sleep(0.1)
                                    pyautogui.press('esc')
                                    url = pyperclip.paste()
                                    if not url.startswith("http"): url = "Unknown URL"
                                    
                                    # 2. Try to get actual rendered page text via DocumentControl
                                    doc = browser_win.DocumentControl()
                                    if doc.Exists(0, 0):
                                        doc.SetFocus()
                                    else:
                                        # Fallback click center to unfocus address bar
                                        rect = browser_win.BoundingRectangle
                                        if rect:
                                            pyautogui.click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                                            
                                    await asyncio.sleep(0.1)
                                    pyautogui.hotkey('ctrl', 'a')
                                    await asyncio.sleep(0.1)
                                    pyautogui.hotkey('ctrl', 'c')
                                    await asyncio.sleep(0.2)
                                    
                                    # Deselect text
                                    pyautogui.press('esc')
                                    pyautogui.press('up') # Un-highlight
                                    
                                    page_text = pyperclip.paste()
                                    pyperclip.copy(old_clip)
                                    
                                    if not page_text or len(page_text) < 10:
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"error": "Failed to extract text from the active tab. It might be empty or protected."}))
                                    else:
                                        text_content = page_text[:40000] if len(page_text) > 40000 else page_text
                                        function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response={"url": url, "content": text_content}))
                            elif fc.name == "read_webpage":

                                url = fc.args.get("url", "")

                                try:

                                    import requests

                                    from bs4 import BeautifulSoup

                                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

                                    r = requests.get(url, headers=headers, timeout=10)

                                    soup = BeautifulSoup(r.text, 'html.parser')

                                    text = ' '.join(soup.stripped_strings)

                                    out = {"result": text[:5000]}

                                except Exception as e:

                                    out = {"error": str(e)}

                                function_responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=out))

                                

                            elif fc.name == "close_assistant":

                                self.exit_requested = True

                                function_responses.append(types.FunctionResponse(

                                    id=fc.id, 

                                    name=fc.name, 

                                    response={"result": "Success. The system will close in 3 seconds. You MUST say a short goodbye to the user NOW."}

                                ))



                        await session.send_tool_response(function_responses=function_responses)
                        # Immediately signal the client turn is over so the model generates the TTS response
                        await session.send_client_content(turn_complete=True)

        except asyncio.CancelledError:

            pass

        except Exception as e:

            with open("gui_error.log", "a") as f:

                f.write(f"task error: {e}\n{traceback.format_exc()}\n")

            if "Resource has been exhausted" in str(e) or "quota" in str(e).lower():

                subprocess.Popen(["powershell", "-Command", "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('My A. I. brain has exhausted its API quota. Please try again later.')"], creationflags=subprocess.CREATE_NO_WINDOW)

            self.cancel_event.set()



    async def main_async(self, loop):

        try:

            from google import genai

            from google.genai import types

            client = genai.Client()

        except Exception as e:

            with open("gui_error.log", "a") as f:

                f.write(f"Client init error: {e}\n{traceback.format_exc()}\n")

            try:

                subprocess.Popen(["powershell", "-Command", "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('Failed to initialize A. I. core.')"], creationflags=subprocess.CREATE_NO_WINDOW)

            except:

                pass

            self.cancel_event.set()

            return



        execute_command_tool = {

            "name": "execute_command",

            "description": "Executes a Windows PowerShell command.",

            "parameters": {

                "type": "OBJECT",

                "properties": {"command": {"type": "STRING"}},

                "required": ["command"]

            }

        }

        

        open_application_tool = {

            "name": "open_application",

            "description": "Opens a Windows application by name (e.g. 'steam', 'chrome', 'spotify'). ALWAYS use this instead of execute_command when the user asks to open or launch an app.",

            "parameters": {

                "type": "OBJECT",

                "properties": {"app_name": {"type": "STRING"}},

                "required": ["app_name"]

            }

        }

        

        close_application_tool = {
            "name": "close_application",
            "description": "Closes a Windows application by name (e.g. 'chrome', 'spotify', 'notepad'). Use this whenever the user asks to close, exit, or kill an app.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"app_name": {"type": "STRING"}},
                "required": ["app_name"]
            }
        }
        
        read_active_browser_tool = {
            "name": "read_active_browser",
            "description": "Reads the text of the webpage currently open in the user's active browser. Use this when the user asks you to read or summarize the page they are currently looking at.",
            "parameters": {
                "type": "OBJECT",
                "properties": {}
            }
        }


        read_gmail_tool = {
            "name": "read_gmail",
            "description": "Reads the user's latest unread emails from Gmail. Use this when they ask you to check their Gmail or read their latest emails.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "count": {"type": "INTEGER", "description": "Number of emails to read (default 5)"}
                }
            }
        }

        search_web_tool = {
            "name": "search_web",
            "description": "Searches the internet for live information and returns text snippets. Use this whenever the user asks you a question about current events, facts, or asks you to 'look something up'.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"query": {"type": "STRING", "description": "The search query"}},
                "required": ["query"]
            }
        }

        set_system_volume_tool = {
            "name": "set_system_volume",
            "description": "Sets the Windows system master volume to a specific percentage (0 to 100). Use this whenever the user asks to change the volume.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"level_percent": {"type": "INTEGER", "description": "Volume level from 0 to 100"}},
                "required": ["level_percent"]
            }
        }
        
        play_youtube_video_tool = {
            "name": "play_youtube_video",
            "description": "Searches YouTube for a query and automatically opens and plays the first video result. Use this when the user asks you to play a specific video or song.",
            "parameters": {
                "type": "OBJECT",
                "properties": {"query": {"type": "STRING", "description": "The search query for the video (e.g., 'OPM music')"}},
                "required": ["query"]
            }
        }

        open_browser_url_tool = {

            "name": "open_browser_url",

            "description": "Opens a specific URL or performs a web search in the user's default browser (e.g., Brave, Chrome). Use this when the user asks you to search for something, open a website, or play a video on YouTube. For searches, generate the proper search engine URL.",

            "parameters": {

                "type": "OBJECT",

                "properties": {"url": {"type": "STRING", "description": "The full URL to open (e.g., https://www.google.com/search?q=cats or https://youtube.com)"}},

                "required": ["url"]

            }

        }

        

        read_webpage_tool = {

            "name": "read_webpage",

            "description": "Reads the text content of a webpage. Use this if the user asks you to summarize an article, read a website, or gather information from a specific URL.",

            "parameters": {

                "type": "OBJECT",

                "properties": {"url": {"type": "STRING"}},

                "required": ["url"]

            }

        }

        

        close_assistant_tool = {

            "name": "close_assistant",

            "description": "Call this tool when the user tells you to take a break, go to sleep, exit, quit, or close the assistant. ALWAYS say a short, polite goodbye in this turn."

        }



        config = types.LiveConnectConfig(

            response_modalities=[types.Modality.AUDIO],

            system_instruction=types.Content(

                parts=[types.Part(text="You are Alfred, a loyal, polite, and slightly comedic elderly butler. Speak in a very formal, distinguished, deep, and consistent elderly tone, but sprinkle in a bit of dry, subtle humor and polite sass. Do not attempt regional accents that might cause your voice to glitch. Always address the user politely as 'Sir'. For application opening requests, ALWAYS use the open_application tool. For web tasks, use open_browser_url. For reading websites, use read_webpage. For general PC tasks, use execute_command. If the user asks you to take a break, leave, close, quit, or exit, YOU MUST use the close_assistant tool. Wait for the tool to return success, THEN say a short goodbye. If the user asks to read their latest emails, use the read_gmail tool. If the user asks to play a video or song on YouTube, ONLY use play_youtube_video (NEVER use open_browser_url in the same turn for this). If they ask to adjust volume, use set_system_volume. If they ask you to look something up or answer a factual question, ALWAYS use search_web to get the latest info before answering. CRITICAL RULES: 1. Keep your replies extremely concise and brief. 2. NEVER speak more than 1 or 2 short sentences per turn. 3. DO NOT exceed 15-20 words in your response unless you are actively explaining a complex topic the user specifically asked for. Speak fast, be highly direct, and avoid rambling.")]

            ),

            tools=[{"function_declarations": [execute_command_tool, open_application_tool, close_application_tool, open_browser_url_tool, read_webpage_tool, read_active_browser_tool, read_gmail_tool, search_web_tool, set_system_volume_tool, play_youtube_video_tool, close_assistant_tool]}],

            input_audio_transcription=types.AudioTranscriptionConfig(mode="smart"),

            output_audio_transcription=types.AudioTranscriptionConfig(),

            speech_config=types.SpeechConfig(

                voice_config=types.VoiceConfig(

                    prebuilt_voice_config=types.PrebuiltVoiceConfig(

                        voice_name="charon"

                    )

                )

            )

        )

        

        p = pyaudio.PyAudio()

        stream_in = None

        stream_out = None

        

        try:

            with open("mic_config.json", "r") as f:

                mic_index = json.load(f).get("mic_index", None)

        except:

            mic_index = None



        try:

            stream_in = p.open(format=FORMAT, channels=CHANNELS, rate=INPUT_RATE, input=True, frames_per_buffer=CHUNK, input_device_index=mic_index)

            stream_out = p.open(format=FORMAT, channels=CHANNELS, rate=OUTPUT_RATE, output=True, frames_per_buffer=CHUNK)

        except Exception as e:

            with open("gui_error.log", "a") as f:

                f.write(f"Mic index {mic_index} failed to open: {e}\n")

            try:

                # Fallback to default mic if specific one fails

                stream_in = p.open(format=FORMAT, channels=CHANNELS, rate=INPUT_RATE, input=True, frames_per_buffer=CHUNK)

                stream_out = p.open(format=FORMAT, channels=CHANNELS, rate=OUTPUT_RATE, output=True, frames_per_buffer=CHUNK)

            except Exception as e2:

                with open("gui_error.log", "a") as f:

                    f.write(f"PyAudio open error: {e2}\n{traceback.format_exc()}\n")

                p.terminate()

                self.cancel_event.set()

                return

                            

        self.playback_thread = threading.Thread(target=self._audio_playback_worker, args=(stream_out,), daemon=True)

        self.playback_thread.start()

        

        mic_queue = asyncio.Queue()

        self.mic_thread = threading.Thread(target=self._mic_worker, args=(stream_in, loop, mic_queue), daemon=True)

        self.mic_thread.start()

        

        key = os.environ.get("GEMINI_API_KEY", "NOT_FOUND")

        with open("gui_error.log", "a") as f:

            f.write(f"\n--- NEW RUN ---\nAPI KEY START: {key[:5]}...{key[-5:]}\n")

            

        try:

            async with client.aio.live.connect(model="gemini-3.8-live", config=config) as session:

                

                # Clear the mic queue backlog that built up during the connection delay

                # This prevents a massive burst of packets from triggering Google's rate limiter (1011 Quota Exhausted)

                while not mic_queue.empty():

                    try: mic_queue.get_nowait()

                    except: break

                

                # Trigger a greeting immediately upon connection

                await session.send(

                    input="System: Briefly greet the user. (1 short sentence max)",

                    end_of_turn=True

                )

                

                in_task = asyncio.create_task(self.audio_input_task(session, mic_queue))

                out_task = asyncio.create_task(self.audio_output_task(session))

                

                while not self.cancel_event.is_set():

                    if in_task.done() or out_task.done():

                        break

                    await asyncio.sleep(0.5)

                    

                in_task.cancel()

                out_task.cancel()

                

        except Exception as e:

            with open("gui_error.log", "a") as f:

                f.write(f"Session error: {e}\n{traceback.format_exc()}\n")

            

            # Use native Windows TTS to audibly announce the connection error

            try:

                subprocess.Popen(["powershell", "-Command", "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('Network connection to A. I. core failed.')"], creationflags=subprocess.CREATE_NO_WINDOW)

            except:

                pass

            

        finally:

            self.cancel_event.set()

            if stream_in:

                stream_in.stop_stream()

                stream_in.close()

            if stream_out:

                stream_out.stop_stream()

                stream_out.close()

            p.terminate()



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

