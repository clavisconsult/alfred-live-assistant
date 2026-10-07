# Alfred: Gemini Live Voice Assistant 🎙️🤖

An ultra-responsive, voice-activated AI assistant built in Python. Powered by **Google's Gemini Live API** (Bidirectional WebSockets) and **Vosk** for offline wake-word detection, Alfred operates as a sleek, frameless JARVIS-style HUD on your desktop.

## Features
- **Instant Wake Word:** Constantly listens in the background for "Alfred" using a lightweight, offline Vosk neural network. Zero battery/CPU drain when the room is silent thanks to an intelligent RMS Noise Gate.
- **Ultra-Low Latency Conversation:** Connects directly to the gemini-3.8-live model over bidirectional WebSockets for human-speed conversational reflexes.
- **Smart Interruption (AEC):** Alfred actively monitors microphone input while speaking. He filters out his own voice bleed but allows you to interrupt him instantly if you speak over him!
- **JARVIS HUD UI:** Frameless, transparent PyQt6 + WebEngine interface with a 3D animated orb. 
- **Tool Calling (Computer Control):** Alfred can open applications, run terminal commands, browse the web, and read websites upon command.
- **Bank-Level Security:** Uses .env for API keys so you never accidentally upload your credentials.
- **Microphone Selection:** Right-click the orb in the system tray to select your hardware microphone and bypass virtual cables (like NVIDIA Broadcast).

## Prerequisites
- Windows 10/11
- Python 3.10+
- A Google Gemini API Key

## Setup Instructions

1. **Clone the repository:**
   \\\ash
   git clone https://github.com/YOUR_USERNAME/alfred-assistant.git
   cd alfred-assistant
   \\\

2. **Install dependencies:**
   \\\ash
   pip install -r requirements.txt
   \\\

3. **Download the Vosk Model:**
   - Download the [Vosk English Model](https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip) (or any language you prefer).
   - Extract the folder and rename it to model.
   - Place the model folder directly inside the project directory.

4. **Add your Gemini API Key:**
   - Create a file named .env in the root folder.
   - Add your key like this:
     \\\env
     GEMINI_API_KEY=AIzaSyYourApiKeyHere...
     \\\

## How to Run

1. **Start the Background Wake Engine:**
   Double-click lfred_wake.pyw. This will run silently in the background and listen for the wake word.
   
2. **Wake Him Up:**
   Simply say **"Alfred"** into your microphone. The HUD will instantly appear and he will greet you.

3. **Manual Start:**
   You can also manually launch the assistant at any time by running:
   \\\ash
   python main_gui.py
   \\\

## Troubleshooting
- **Cannot Hear You?** Right-click the Alfred icon in your Windows System Tray (bottom right) and click "Select Microphone". Ensure you have a physical microphone selected, not a virtual cable that might be muted.
- **Quota / 1011 Error:** This usually means the API key is incorrect, or you have launched multiple instances of the assistant at the same time. Ensure all background pythonw.exe tasks are closed.

---
*Disclaimer: This is a hobby project. Be careful when granting the AI terminal access (execute_command tool) on your main machine.*
