import sys
import winsound
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont, QColor, QPainter

class AlfredTimer(QWidget):
    def __init__(self, minutes, label):
        super().__init__()
        self.total_seconds = int(minutes * 60)
        self.label_text = label
        self.initUI()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)

    def initUI(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(250, 110)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(15, 15, 15, 15)
        
        self.lbl_title = QLabel(self.label_text)
        self.lbl_title.setStyleSheet("color: #00FFCC; font-size: 14px; font-weight: bold; font-family: Segoe UI;")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_time = QLabel(self.format_time(self.total_seconds))
        self.lbl_time.setStyleSheet("color: white; font-size: 32px; font-weight: bold; font-family: Segoe UI;")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_dismiss = QPushButton("Dismiss")
        self.btn_dismiss.setStyleSheet("background-color: #00FFCC; color: black; font-weight: bold; border-radius: 5px; padding: 5px;")
        self.btn_dismiss.clicked.connect(self.close_alarm)
        self.btn_dismiss.hide()

        self.layout.addWidget(self.lbl_title)
        self.layout.addWidget(self.lbl_time)
        self.layout.addWidget(self.btn_dismiss)
        self.setLayout(self.layout)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 280, 50)
        self.oldPos = self.pos()

    def format_time(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def update_time(self):
        if self.total_seconds > 0:
            self.total_seconds -= 1
            self.lbl_time.setText(self.format_time(self.total_seconds))
        else:
            self.timer.stop()
            self.lbl_time.setStyleSheet("color: #FF3366; font-size: 32px; font-weight: bold; font-family: Segoe UI;")
            self.btn_dismiss.show()
            self.resize(250, 140)
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_LOOP | winsound.SND_ASYNC)

    def close_alarm(self):
        winsound.PlaySound(None, winsound.SND_PURGE)
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(20, 20, 20, 220))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 15.0, 15.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.oldPos = event.globalPosition().toPoint()
            
    def mouseMoveEvent(self, event):
        if hasattr(self, 'oldPos') and self.oldPos:
            delta = event.globalPosition().toPoint() - self.oldPos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.oldPos = event.globalPosition().toPoint()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    mins = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05
    lbl = sys.argv[2] if len(sys.argv) > 2 else "Test Popup"
    ex = AlfredTimer(mins, lbl)
    ex.show()
    sys.exit(app.exec())
