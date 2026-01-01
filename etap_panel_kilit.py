import sys
import socket
import paramiko
import json
import os
from datetime import datetime
from threading import Thread  # Hatanın çözümü için kritik satır
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import QPixmap, QFont

# Pardus 25 ve Wayland uyumluluğu için X11 zorlaması
os.environ["QT_QPA_PLATFORM"] = "xcb"

# --- Kurumsal Stil (Pardus 25 Estetiği) ---
STYLE_SHEET = """
QMainWindow { background-color: #f0f2f5; }
QFrame#Header { background-color: #ffffff; border-bottom: 3px solid #3498db; }
QLabel#SchoolTitle { color: #2c3e50; font-size: 16px; font-weight: bold; }
QPushButton { border-radius: 5px; padding: 10px; font-weight: bold; border: 1px solid #ced4da; background-color: white; }
QPushButton#BtnLock { background-color: #d63031; color: white; border: none; }
QPushButton#BtnUnlock { background-color: #27ae60; color: white; border: none; }
QPushButton#BtnAction { background-color: #3498db; color: white; border: none; }
QListWidget, QTableWidget { background-color: white; border: 1px solid #dee2e6; border-radius: 4px; }
QLineEdit { padding: 5px; border: 1px solid #ced4da; border-radius: 4px; }
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

class BoardWorker:
    def run_ssh(self, ip, user, password, action):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, username=user, password=password, timeout=5)
            if action == "lock":
                cmd = "dbus-send --system --dest=org.freedesktop.DisplayManager --type=method_call /org/freedesktop/DisplayManager/Seat0 org.freedesktop.DisplayManager.Seat.Lock"
            else:
                cmd = "export DISPLAY=:0; cinnamon-screensaver-command -d"
            ssh.exec_command(cmd)
            ssh.close()
        except Exception as e:
            print(f"Hata ({ip}): {e}")

class EtapKilitPaneli(QMainWindow):
    tahta_bulundu_sinyali = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TSOMTAL ETAP Merkezi Kilit Paneli")
        self.setMinimumSize(1200, 750)
        self.setStyleSheet(STYLE_SHEET)

        # Varsayılan Ağ Bloğu 10.46.197 olarak ayarlandı
        self.config = DataManager.load("ayarlar.json", {
            "user": "etapadmin", 
            "pass": "etap+pardus!", 
            "ip_range": "10.46.197"
        })
        self.schedule = DataManager.load("program.json", {day: [] for day in ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]})

        self.init_ui()
        self.tahta_bulundu_sinyali.connect(self.board_list.addItem)
        
        # Zil Kontrol Zamanlayıcısı
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_bell_mode)
        self.timer.start(30000)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0,0,0,0)

        # --- ÜST BİLGİ ALANI ---
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(110)
        h_layout = QHBoxLayout(header)

        logo = QLabel()
        pix = QPixmap("school_logo.png")
        if not pix.isNull():
            logo.setPixmap(pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        h_layout.addWidget(logo)

        title = QLabel("KAHRAMANMARAŞ / ONİKİŞUBAT\nTicaret ve Sanayi Odası Ticaret Mesleki ve Teknik Anadolu Lisesi")
        title.setObjectName("SchoolTitle")
        h_layout.addWidget(title)
        h_layout.addStretch()

        self.clock_lbl = QLabel()
        self.clock_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        h_layout.addWidget(self.clock_lbl)
        
        timer = QTimer(self)
        timer.timeout.connect(lambda: self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S")))
        timer.start(1000)
        main_layout.addWidget(header)

        # --- ANA GÖVDE ---
        body = QHBoxLayout()
        body.setContentsMargins(15,15,15,15)
        body.setSpacing(15)

        # Sol: Ağ
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("<b>AĞ TARAMA</b>"))
        self.ip_in = QLineEdit(self.config["ip_range"])
        col1.addWidget(self.ip_in)
        btn_scan = QPushButton("🔍 Tahtaları Tara")
        btn_scan.setObjectName("BtnAction")
        btn_scan.clicked.connect(self.scan_network)
        col1.addWidget(btn_scan)
        self.board_list = QListWidget()
        self.board_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        col1.addWidget(self.board_list)
        body.addLayout(col1, 2)

        # Orta: Manuel
        col2 = QVBoxLayout()
        col2.addWidget(QLabel("<b>YÖNETİCİ</b>"))
        self.u_in = QLineEdit(self.config["user"])
        self.p_in = QLineEdit(self.config["pass"])
        self.p_in.setEchoMode(QLineEdit.EchoMode.Password)
        col2.addWidget(QLabel("Kullanıcı:"))
        col2.addWidget(self.u_in)
        col2.addWidget(QLabel("Şifre:"))
        col2.addWidget(self.p_in)
        col2.addSpacing(30)
        btn_l = QPushButton("🔒 KİLİTLE")
        btn_l.setObjectName("BtnLock")
        btn_l.setFixedHeight(50)
        btn_l.clicked.connect(lambda: self.manage_boards("lock"))
        col2.addWidget(btn_l)
        btn_u = QPushButton("🔓 AÇ")
        btn_u.setObjectName("BtnUnlock")
        btn_u.setFixedHeight(50)
        btn_u.clicked.connect(lambda: self.manage_boards("unlock"))
        col2.addWidget(btn_u)
        col2.addStretch()
        body.addLayout(col2, 1)

        # Sağ: Zil
        col3 = QVBoxLayout()
        col3.addWidget(QLabel("<b>ZİL MODU</b>"))
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
        
        btn_save = QPushButton("💾 TÜMÜNÜ KAYDET")
        btn_save.setObjectName("BtnAction")
        btn_save.clicked.connect(self.save_all)
        col3.addWidget(btn_save)
        body.addLayout(col3, 2)

        main_layout.addLayout(body)
        self.load_day()

    def scan_network(self):
        self.board_list.clear()
        prefix = self.ip_in.text()
        def wrk():
            for i in range(1, 255):
                ip = f"{prefix}.{i}"
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    if s.connect_ex((ip, 22)) == 0:
                        self.tahta_bulundu_sinyali.emit(ip)
        Thread(target=wrk, daemon=True).start()

    def manage_boards(self, act):
        for item in self.board_list.selectedItems():
            Thread(target=BoardWorker().run_ssh, args=(item.text(), self.u_in.text(), self.p_in.text(), act), daemon=True).start()

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
        cur_t = now.strftime("%H:%M")
        cur_d = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][now.weekday()]
        for s in self.schedule.get(cur_d, []):
            if s["start"] <= cur_t <= s["end"]:
                for i in range(self.board_list.count()):
                    Thread(target=BoardWorker().run_ssh, args=(self.board_list.item(i).text(), self.u_in.text(), self.p_in.text(), s["action"]), daemon=True).start()
                break

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = EtapKilitPaneli()
    win.show()
    sys.exit(app.exec())
