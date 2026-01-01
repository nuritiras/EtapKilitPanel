import sys
import socket
import paramiko
import json
import os
import time
from datetime import datetime
from threading import Thread
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import QPixmap, QFont

# Pardus 25 / Wayland uyumu için
os.environ["QT_QPA_PLATFORM"] = "xcb"

# --- Stil Yapılandırması (TSOMTAL & Pardus 25) ---
STYLE_SHEET = """
QMainWindow { background-color: #f8f9fa; }
QFrame#Header { background-color: #ffffff; border-bottom: 3px solid #3498db; }
QLabel#SchoolTitle { color: #2c3e50; font-size: 15px; font-weight: bold; }
QProgressBar {
    border: 1px solid #bdc3c7;
    border-radius: 0px;
    text-align: center;
    background-color: #ecf0f1;
    height: 22px;
    font-size: 11px;
    font-weight: bold;
}
QProgressBar::chunk { background-color: #27ae60; }
QPushButton { border-radius: 5px; padding: 10px; font-weight: bold; border: 1px solid #dcdde1; background-color: white; }
QPushButton#BtnLock { background-color: #e74c3c; color: white; border: none; }
QPushButton#BtnUnlock { background-color: #2ecc71; color: white; border: none; }
QPushButton#BtnAction { background-color: #3498db; color: white; border: none; }
"""

class DataManager:
    @staticmethod
    def save(file, data):
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    @staticmethod
    def load(file, default):
        if os.path.exists(file):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: return default
        return default

class EtapKilitPaneli(QMainWindow):
    found_ip_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    progress_visible_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TSOMTAL ETAP Merkezi Yönetim Sistemi v9")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(STYLE_SHEET)

        # CIDR 10.46.197.0/24 formatında varsayılan ağ
        self.config = DataManager.load("ayarlar.json", {
            "user": "etapadmin", 
            "pass": "etap+pardus!", 
            "ip_range": "10.46.197.0/24"
        })
        self.schedule = DataManager.load("program.json", {day: [] for day in ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]})

        self.init_ui()
        
        # UI Güncelleme Bağlantıları
        self.found_ip_signal.connect(self.board_list.addItem)
        self.progress_signal.connect(self.pbar.setValue)
        self.progress_visible_signal.connect(self.pbar.setVisible)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_bell_mode)
        self.timer.start(30000)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        # --- ÜST PANEL ---
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(110)
        h_layout = QHBoxLayout(header)

        logo = QLabel()
        pix = QPixmap("school_logo.png")
        if not pix.isNull():
            logo.setPixmap(pix.scaled(85, 85, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        h_layout.addWidget(logo)

        title = QLabel("KAHRAMANMARAŞ / ONİKİŞUBAT\nTicaret ve Sanayi Odası Ticaret Mesleki ve Teknik Anadolu Lisesi")
        title.setObjectName("SchoolTitle")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self.clock_lbl = QLabel()
        self.clock_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #34495e;")
        h_layout.addWidget(self.clock_lbl)
        
        t_timer = QTimer(self)
        t_timer.timeout.connect(lambda: self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S")))
        t_timer.start(1000)
        main_layout.addWidget(header)

        # --- ORTA İÇERİK ---
        body_widget = QWidget()
        body = QHBoxLayout(body_widget)
        body.setContentsMargins(20,20,20,20)
        body.setSpacing(20)

        # Sol
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("<b>AĞ TARAMA (CIDR: 10.46.197.0/24)</b>"))
        self.ip_in = QLineEdit(self.config["ip_range"])
        col1.addWidget(self.ip_in)
        btn_scan = QPushButton("🔍 Tahtaları Tara")
        btn_scan.setObjectName("BtnAction")
        btn_scan.clicked.connect(self.start_scan)
        col1.addWidget(btn_scan)
        self.board_list = QListWidget()
        self.board_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        col1.addWidget(self.board_list)
        body.addLayout(col1, 2)

        # Orta
        col2 = QVBoxLayout()
        col2.addWidget(QLabel("<b>YÖNETİCİ</b>"))
        self.u_in = QLineEdit(self.config["user"])
        self.p_in = QLineEdit(self.config["pass"])
        self.p_in.setEchoMode(QLineEdit.EchoMode.Password)
        col2.addWidget(QLabel("Kullanıcı:"))
        col2.addWidget(self.u_in)
        col2.addWidget(QLabel("Şifre:"))
        col2.addWidget(self.p_in)
        col2.addSpacing(40)
        btn_l = QPushButton("🔒 SEÇİLİLERİ KİLİTLE")
        btn_l.setObjectName("BtnLock")
        btn_l.setFixedHeight(55)
        btn_l.clicked.connect(lambda: self.start_manage("lock"))
        col2.addWidget(btn_l)
        btn_u = QPushButton("🔓 SEÇİLİLERİ AÇ")
        btn_u.setObjectName("BtnUnlock")
        btn_u.setFixedHeight(55)
        btn_u.clicked.connect(lambda: self.start_manage("unlock"))
        col2.addWidget(btn_u)
        col2.addStretch()
        body.addLayout(col2, 1)

        # Sağ
        col3 = QVBoxLayout()
        col3.addWidget(QLabel("<b>ZİL MODU PROGRAMI</b>"))
        self.day_cb = QComboBox()
        self.day_cb.addItems(self.schedule.keys())
        self.day_cb.currentIndexChanged.connect(self.load_day)
        col3.addWidget(self.day_cb)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Başlangıç", "Bitiş", "İşlem"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        col3.addWidget(self.table)
        
        h_btns = QHBoxLayout()
        btn_add = QPushButton("+ Ekle")
        btn_add.clicked.connect(self.add_slot)
        btn_copy = QPushButton("📅 Haftaya Yay")
        btn_copy.clicked.connect(self.copy_all)
        h_btns.addWidget(btn_add)
        h_btns.addWidget(btn_copy)
        col3.addLayout(h_btns)
        
        btn_save = QPushButton("💾 PROGRAMI KAYDET")
        btn_save.setObjectName("BtnAction")
        btn_save.clicked.connect(self.save_all)
        col3.addWidget(btn_save)
        body.addLayout(col3, 2)

        main_layout.addWidget(body_widget)

        # --- ALT PANEL: PROGRESS BAR (İsteğiniz üzere en altta) ---
        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        self.pbar.setVisible(False)
        main_layout.addWidget(self.pbar)
        
        self.load_day()

    # --- SSH VE TARAMA MANTIĞI ---
    def start_scan(self):
        self.board_list.clear()
        self.progress_visible_signal.emit(True)
        # CIDR Ayrıştırma: 10.46.197.0/24 -> 10.46.197
        raw_ip = self.ip_in.text().split('/')[0]
        prefix = ".".join(raw_ip.split('.')[:3])
        
        def run():
            for i in range(1, 255):
                ip = f"{prefix}.{i}"
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.04)
                    if s.connect_ex((ip, 22)) == 0:
                        self.found_ip_signal.emit(ip)
                self.progress_signal.emit(int((i / 254) * 100))
            time.sleep(0.5)
            self.progress_visible_signal.emit(False)

        Thread(target=run, daemon=True).start()

    def start_manage(self, action):
        selected = [item.text() for item in self.board_list.selectedItems()]
        if not selected: return
        self.progress_visible_signal.emit(True)
        
        def run():
            total = len(selected)
            for idx, ip in enumerate(selected):
                self.execute_ssh(ip, action)
                self.progress_signal.emit(int(((idx + 1) / total) * 100))
            time.sleep(1)
            self.progress_visible_signal.emit(False)

        Thread(target=run, daemon=True).start()

    def execute_ssh(self, ip, action):
        user, pw = self.u_in.text(), self.p_in.text()
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, username=user, password=pw, timeout=5)
            
            if action == "lock":
                # Kesin Kilitleme
                cmd = "dbus-send --system --dest=org.freedesktop.DisplayManager --type=method_call /org/freedesktop/DisplayManager/Seat0 org.freedesktop.DisplayManager.Seat.Lock"
            else:
                # KESİN KİLİT AÇMA (Pardus ETAP 23/25 Çözümü):
                # 1. loginctl ile sistem kilidini düşür.
                # 2. Oturum sahibinin DBus kanalına sız ve ScreenSaver'ı kapat.
                cmd = (
                    "export DISPLAY=:0; "
                    "loginctl unlock-sessions; "
                    "ACT_USR=$(stat -c '%U' /dev/tty7 2>/dev/null || echo 'etapadmin'); "
                    "USR_ID=$(id -u $ACT_USR); "
                    "export XDG_RUNTIME_DIR=/run/user/$USR_ID; "
                    "export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$USR_ID/bus; "
                    "dbus-send --session --dest=org.cinnamon.ScreenSaver --type=method_call /org/cinnamon/ScreenSaver org.cinnamon.ScreenSaver.SetActive boolean:false"
                )
            
            ssh.exec_command(cmd)
            ssh.close()
        except Exception as e:
            print(f"Hata {ip}: {e}")

    # --- DİĞER YARDIMCI FONKSİYONLAR ---
    def add_slot(self, s="08:10", e="08:50", a="unlock"):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(s))
        self.table.setItem(row, 1, QTableWidgetItem(e))
        cb = QComboBox()
        cb.addItems(["Kilitle", "Aç"])
        cb.setCurrentIndex(0 if a == "lock" else 1)
        self.table.setCellWidget(row, 2, cb)

    def load_day(self):
        self.table.setRowCount(0)
        for s in self.schedule.get(self.day_cb.currentText(), []):
            self.add_slot(s["start"], s["end"], s["action"])

    def save_all(self):
        self.config.update({"user": self.u_in.text(), "pass": self.p_in.text(), "ip_range": self.ip_in.text()})
        DataManager.save("ayarlar.json", self.config)
        slots = []
        for r in range(self.table.rowCount()):
            slots.append({"start": self.table.item(r, 0).text(), "end": self.table.item(r, 1).text(), "action": "lock" if self.table.cellWidget(r, 2).currentIndex() == 0 else "unlock"})
        self.schedule[self.day_cb.currentText()] = slots
        DataManager.save("program.json", self.schedule)
        QMessageBox.information(self, "Bilgi", "Ayarlar ve program kaydedildi.")

    def copy_all(self):
        slots = []
        for r in range(self.table.rowCount()):
            slots.append({"start": self.table.item(r, 0).text(), "end": self.table.item(r, 1).text(), "action": "lock" if self.table.cellWidget(r, 2).currentIndex() == 0 else "unlock"})
        for d in self.schedule.keys():
            self.schedule[d] = list(slots)
        DataManager.save("program.json", self.schedule)
        QMessageBox.information(self, "Bilgi", "Program tüm haftaya kopyalandı.")

    def check_bell_mode(self):
        now = datetime.now()
        cur_t, cur_d = now.strftime("%H:%M"), ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][now.weekday()]
        for s in self.schedule.get(cur_d, []):
            if s["start"] <= cur_t <= s["end"]:
                for i in range(self.board_list.count()):
                    self.execute_ssh(self.board_list.item(i).text(), s["action"])
                break

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = EtapKilitPaneli()
    win.show()
    sys.exit(app.exec())
