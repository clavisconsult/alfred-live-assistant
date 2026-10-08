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

words = ["alfred", "hey alfred", "wake up alfred", "hello alfred", "[unk]",
    "the", "of", "to", "and", "a", "in", "is", "it", "you", "that", "he", "was", "for", "on", "are", "with", "as", "i", "his", "they", "be", "at", "one", "have", "this", "from", "or", "had", "by", "not", "word", "but", "what", "some", "we", "can", "out", "other", "were", "all", "there", "when", "up", "use", "your", "how", "said", "an", "each", "she", "which", "do", "their", "time", "if", "will", "way", "about", "many", "then", "them", "write", "would", "like", "so", "these", "her", "long", "make", "thing", "see", "him", "two", "has", "look", "more", "day", "could", "go", "come", "did", "number", "sound", "no", "most", "people", "my", "over", "know", "water", "than", "call", "first", "who", "may", "down", "side", "been", "now", "find", "any", "new", "work", "part", "take", "get", "place", "made", "live", "where", "after", "back", "little", "only", "round", "man", "year", "came", "show", "every", "good", "me", "give", "our", "under", "name", "very", "through", "just", "form", "sentence", "great", "think", "say", "help", "low", "line", "differ", "turn", "cause", "much", "mean", "before", "move", "right", "boy", "old", "too", "same", "tell", "does", "set", "three", "want", "air", "well", "also", "play", "small", "end", "put", "home", "read", "hand", "port", "large", "spell", "add", "even", "land", "here", "must", "big", "high", "such", "follow", "act", "why", "ask", "men", "change", "went", "light", "kind", "off", "need", "house", "picture", "try", "us", "again", "animal", "point", "mother", "world", "near", "build", "self", "earth", "father", "head", "stand", "own", "page", "should", "country", "found", "answer", "school", "grow", "study", "still", "learn", "plant", "cover", "food", "sun", "four", "between", "state", "keep", "eye", "never", "last", "let", "thought", "city", "tree", "cross", "farm", "hard", "start", "might", "story", "saw", "far", "sea", "draw", "left", "late", "run", "don't", "while", "press", "close", "night", "real", "life", "few", "north", "open", "seem", "together", "next", "white", "children", "begin", "got", "walk", "example", "ease", "paper", "group", "always", "music", "those", "both", "mark", "often", "letter", "until", "mile", "river", "car", "feet", "care", "second", "book", "carry", "took", "science", "eat", "room", "friend", "began", "idea", "fish", "mountain", "stop", "once", "base", "hear", "horse", "cut", "sure", "watch", "color", "face", "wood", "main", "enough", "plain", "girl", "usual", "young", "ready", "above", "ever", "red", "list", "though", "feel", "talk", "bird", "soon", "body", "dog", "family", "direct", "pose", "leave", "song", "measure", "door", "product", "black", "short", "numeral", "class", "wind", "question", "happen", "complete", "ship", "area", "half", "rock", "order", "fire", "south", "problem", "piece", "told", "knew", "pass", "since", "top", "whole", "king", "space", "heard", "best", "hour", "better", "true", "during", "hundred", "five", "remember", "step", "early", "hold", "west", "ground", "interest", "reach", "fast", "verb", "sing", "listen", "six", "table", "travel", "less", "morning", "ten", "simple", "several", "vowel", "toward", "war", "lay", "against", "pattern", "slow", "center", "love", "person", "money", "serve", "appear", "road", "map", "rain", "rule", "govern", "pull", "cold", "notice", "voice", "unit", "power", "town", "fine", "certain", "fly", "fall", "lead", "cry", "dark", "machine", "note", "wait", "plan", "figure", "star", "box", "noun", "field", "rest", "correct", "able", "pound", "done", "beauty", "drive", "stood", "contain", "front", "teach", "week", "final", "gave", "green", "oh", "quick", "develop", "ocean", "warm", "free", "minute", "strong", "special", "mind", "behind", "clear", "tail", "produce", "fact", "street", "inch", "multiply", "nothing", "course", "stay", "wheel", "full", "force", "blue", "object", "decide", "surface", "deep", "moon", "island", "foot", "system", "busy", "test", "record", "boat", "common", "gold", "possible", "plane", "stead", "dry", "wonder", "laugh", "thousand", "ago", "ran", "check", "game", "shape", "equate", "hot", "miss", "brought", "heat", "snow", "tire", "bring", "yes", "distant", "fill", "east", "paint", "language", "among"]
import json
grammar = json.dumps(words)
recognizer = vosk.KaldiRecognizer(model, 16000, grammar)
recognizer.SetWords(True)



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
                        
                valid_wake = False
                if "alfred" in text.lower():
                    if "result" in res:
                        for word_data in res["result"]:
                            if "alfred" in word_data.get("word", "").lower():
                                conf = word_data.get("conf", 1.0)
                                if conf >= 0.50:
                                    valid_wake = True
                                else:
                                    pass
                    else:
                        valid_wake = True
                if valid_wake:
                if valid_wake:
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
