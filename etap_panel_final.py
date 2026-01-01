import sys
import socket
import paramiko
import json
import os
import time
from datetime import datetime, timedelta
from threading import Thread
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import QPixmap, QFont

# Pardus 25 / Wayland uyumluluğu
os.environ["QT_QPA_PLATFORM"] = "xcb"

# --- Stil Yapılandırması (TSOMTAL Kurumsal) ---
STYLE_SHEET = """
QMainWindow { background-color: #f4f7f6; }
QFrame#Header { background-color: #ffffff; border-bottom: 3px solid #3498db; }
QLabel#SchoolTitle { color: #2c3e50; font-size: 15px; font-weight: bold; }
QGroupBox { font-weight: bold; border: 1px solid #dcdde1; margin-top: 10px; padding: 10px; border-radius: 5px; }
QProgressBar { 
    border: 1px solid #bdc3c7; 
    text-align: center; 
    height: 25px; 
    font-size: 11px; 
    font-weight: bold;
    background-color: #ecf0f1;
    border-radius: 0px;
}
QProgressBar::chunk { background-color: #27ae60; }
QPushButton { border-radius: 4px; padding: 8px; font-weight: bold; border: 1px solid #dcdde1; background-color: white; }
QPushButton#BtnLock { background-color: #e74c3c; color: white; border: none; }
QPushButton#BtnUnlock { background-color: #2ecc71; color: white; border: none; }
QPushButton#BtnAction { background-color: #3498db; color: white; border: none; }
"""

class DataManager:
    SETTINGS_FILE = "ayarlar.json"
    SCHEDULE_FILE = "program.json"
    IPS_FILE = "tahtalar.json"

    @staticmethod
    def save_json(file, data):
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    @staticmethod
    def load_json(file, default):
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
        self.setWindowTitle("TSOMTAL ETAP Merkezi Yönetim Paneli v13")
        self.setMinimumSize(1250, 850)
        self.setStyleSheet(STYLE_SHEET)

        # Veri Yükleme
        self.config = DataManager.load_json(DataManager.SETTINGS_FILE, {
            "user": "etapadmin", "pass": "etap+pardus!", "ip_range": "10.46.197.0/24"
        })
        self.schedule = DataManager.load_json(DataManager.SCHEDULE_FILE, {day: [] for day in ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]})
        self.saved_ips = DataManager.load_json(DataManager.IPS_FILE, [])

        self.init_ui()
        
        # Sinyal Bağlantıları
        self.found_ip_signal.connect(self.board_list.addItem)
        self.progress_signal.connect(self.pbar.setValue)
        self.progress_visible_signal.connect(self.pbar.setVisible)
        
        # Kayıtlı IP'leri Yükle
        if self.saved_ips:
            self.board_list.addItems(self.saved_ips)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_bell_mode)
        self.timer.start(30000)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        # --- ÜST PANEL (Logo ve Okul Adı) ---
        header = QFrame(); header.setObjectName("Header"); header.setFixedHeight(110)
        h_layout = QHBoxLayout(header)
        
        logo = QLabel()
        pix = QPixmap("school_logo.png")
        if not pix.isNull():
            logo.setPixmap(pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        h_layout.addWidget(logo)

        title = QLabel("KAHRAMANMARAŞ / ONİKİŞUBAT\nTicaret ve Sanayi Odası Ticaret Mesleki ve Teknik Anadolu Lisesi")
        title.setObjectName("SchoolTitle"); h_layout.addWidget(title)
        
        h_layout.addStretch()
        self.clock_lbl = QLabel()
        self.clock_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        h_layout.addWidget(self.clock_lbl)
        main_layout.addWidget(header)
        
        timer = QTimer(self); timer.timeout.connect(lambda: self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S"))); timer.start(1000)

        # --- ANA GÖVDE ---
        body_widget = QWidget()
        body = QHBoxLayout(body_widget)
        body.setContentsMargins(15,15,15,15); body.setSpacing(15)

        # SOL: AĞ VE IP LİSTESİ
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("<b>AĞ TARAMA VE KAYITLI TAHTALAR</b>"))
        self.ip_in = QLineEdit(self.config["ip_range"]); col1.addWidget(self.ip_in)
        btn_h = QHBoxLayout()
        btn_scan = QPushButton("🔍 Tahtaları Tara"); btn_scan.setObjectName("BtnAction"); btn_scan.clicked.connect(self.start_scan)
        btn_clear = QPushButton("🗑 Listeyi Temizle"); btn_clear.clicked.connect(self.clear_list)
        btn_h.addWidget(btn_scan); btn_h.addWidget(btn_clear)
        col1.addLayout(btn_h)
        self.board_list = QListWidget(); self.board_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection); col1.addWidget(self.board_list)
        body.addLayout(col1, 2)

        # ORTA: MANUEL KONTROL
        col2 = QVBoxLayout()
        col2.addWidget(QLabel("<b>YÖNETİCİ GİRİŞİ</b>"))
        self.u_in = QLineEdit(self.config["user"]); self.p_in = QLineEdit(self.config["pass"]); self.p_in.setEchoMode(QLineEdit.EchoMode.Password)
        col2.addWidget(QLabel("SSH Kullanıcı:")); col2.addWidget(self.u_in)
        col2.addWidget(QLabel("SSH Parola:")); col2.addWidget(self.p_in)
        col2.addSpacing(30)
        btn_l = QPushButton("🔒 SEÇİLİLERİ KİLİTLE"); btn_l.setObjectName("BtnLock"); btn_l.setFixedHeight(50); btn_l.clicked.connect(lambda: self.start_manage("lock")); col2.addWidget(btn_l)
        btn_u = QPushButton("🔓 SEÇİLİLERİ AÇ"); btn_u.setObjectName("BtnUnlock"); btn_u.setFixedHeight(50); btn_u.clicked.connect(lambda: self.start_manage("unlock")); col2.addWidget(btn_u)
        col2.addStretch()
        body.addLayout(col2, 1)

        # SAĞ: ZİL MODU VE SİHİRBAZ
        col3 = QVBoxLayout()
        wiz_group = QGroupBox("Program Sihirbazı")
        wiz_layout = QGridLayout()
        self.start_time = QTimeEdit(QTime(8, 10)); wiz_layout.addWidget(QLabel("Başlangıç:"), 0, 0); wiz_layout.addWidget(self.start_time, 0, 1)
        self.lesson_dur = QSpinBox(); self.lesson_dur.setValue(40); wiz_layout.addWidget(QLabel("Ders (dk):"), 0, 2); wiz_layout.addWidget(self.lesson_dur, 0, 3)
        self.break_dur = QSpinBox(); self.break_dur.setValue(10); wiz_layout.addWidget(QLabel("Tenefüs (dk):"), 1, 0); wiz_layout.addWidget(self.break_dur, 1, 1)
        self.lunch_after = QSpinBox(); self.lunch_after.setValue(4); wiz_layout.addWidget(QLabel("Öğle Arası (Ders):"), 1, 2); wiz_layout.addWidget(self.lunch_after, 1, 3)
        self.lunch_dur = QSpinBox(); self.lunch_dur.setValue(45); wiz_layout.addWidget(QLabel("Öğle (dk):"), 2, 0); wiz_layout.addWidget(self.lunch_dur, 2, 1)
        self.lesson_count = QSpinBox(); self.lesson_count.setValue(8); wiz_layout.addWidget(QLabel("Ders Sayısı:"), 2, 2); wiz_layout.addWidget(self.lesson_count, 2, 3)
        btn_gen = QPushButton("🪄 Tabloyu Otomatik Doldur"); btn_gen.clicked.connect(self.generate_daily_schedule); wiz_layout.addWidget(btn_gen, 3, 0, 1, 4)
        wiz_group.setLayout(wiz_layout); col3.addWidget(wiz_group)

        self.day_cb = QComboBox(); self.day_cb.addItems(self.schedule.keys()); self.day_cb.currentIndexChanged.connect(self.load_day); col3.addWidget(self.day_cb)
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(["Başlangıç", "Bitiş", "İşlem"]); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); col3.addWidget(self.table)
        
        h_btns_right = QHBoxLayout()
        btn_copy = QPushButton("📅 Tüm Haftaya Kopyala"); btn_copy.clicked.connect(self.copy_all)
        btn_save = QPushButton("💾 AYARLARI KAYDET"); btn_save.setObjectName("BtnAction"); btn_save.clicked.connect(self.save_all)
        h_btns_right.addWidget(btn_copy); h_btns_right.addWidget(btn_save)
        col3.addLayout(h_btns_right)
        body.addLayout(col3, 3)

        main_layout.addWidget(body_widget)

        # --- EN ALT PANEL (PROGRESS BAR) ---
        self.pbar = QProgressBar()
        self.pbar.setVisible(False)
        main_layout.addWidget(self.pbar)
        
        self.load_day()

    # --- IP YÖNETİMİ ---
    def clear_list(self):
        self.board_list.clear()
        DataManager.save_json(DataManager.IPS_FILE, [])

    def start_scan(self):
        self.board_list.clear()
        self.progress_visible_signal.emit(True)
        prefix = ".".join(self.ip_in.text().split('/')[0].split('.')[:3])
        
        def run():
            current_found = []
            for i in range(1, 255):
                ip = f"{prefix}.{i}"
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.04)
                    if s.connect_ex((ip, 22)) == 0:
                        self.found_ip_signal.emit(ip)
                        current_found.append(ip)
                self.progress_signal.emit(int((i / 254) * 100))
            
            DataManager.save_json(DataManager.IPS_FILE, current_found)
            time.sleep(1); self.progress_visible_signal.emit(False)
            
        Thread(target=run, daemon=True).start()

    def start_manage(self, action):
        selected = [item.text() for item in self.board_list.selectedItems()]
        if not selected: return
        self.progress_visible_signal.emit(True)
        
        def run():
            total = len(selected)
            for idx, ip in enumerate(selected):
                self.execute_ssh(ip, action)
                self.progress_signal.emit(int(((idx+1)/total)*100))
            time.sleep(1); self.progress_visible_signal.emit(False)
        Thread(target=run, daemon=True).start()

    def execute_ssh(self, ip, action):
        try:
            ssh = paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, username=self.u_in.text(), password=self.p_in.text(), timeout=4)
            if action == "lock":
                cmd = "dbus-send --system --dest=org.freedesktop.DisplayManager --type=method_call /org/freedesktop/DisplayManager/Seat0 org.freedesktop.DisplayManager.Seat.Lock"
            else:
                # Kesin Çözüm Kilit Açma
                cmd = "dbus-send --system --dest=org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager.UnlockSessions"
            ssh.exec_command(cmd); ssh.close()
        except: pass

    # --- DİĞER FONKSİYONLAR ---
    def generate_daily_schedule(self):
        self.table.setRowCount(0)
        current_dt = datetime.combine(datetime.today(), self.start_time.time().toPyTime())
        for i in range(1, self.lesson_count.value() + 1):
            s_str = current_dt.strftime("%H:%M")
            current_dt += timedelta(minutes=self.lesson_dur.value())
            e_str = current_dt.strftime("%H:%M")
            self.add_slot(s_str, e_str, "unlock")
            if i < self.lesson_count.value():
                b_start = current_dt.strftime("%H:%M")
                dur = self.lunch_dur.value() if i == self.lunch_after.value() else self.break_dur.value()
                current_dt += timedelta(minutes=dur)
                b_end = current_dt.strftime("%H:%M")
                self.add_slot(b_start, b_end, "lock")

    def add_slot(self, s, e, a):
        row = self.table.rowCount(); self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(s)); self.table.setItem(row, 1, QTableWidgetItem(e))
        cb = QComboBox(); cb.addItems(["Kilitle (Tenefüs)", "Aç (Ders)"]); cb.setCurrentIndex(0 if a == "lock" else 1)
        self.table.setCellWidget(row, 2, cb)

    def load_day(self):
        self.table.setRowCount(0)
        for s in self.schedule.get(self.day_cb.currentText(), []): self.add_slot(s["start"], s["end"], s["action"])

    def save_all(self):
        self.config.update({"user": self.u_in.text(), "pass": self.p_in.text(), "ip_range": self.ip_in.text()})
        DataManager.save_json(DataManager.SETTINGS_FILE, self.config)
        slots = [{"start": self.table.item(r,0).text(), "end": self.table.item(r,1).text(), "action": "lock" if self.table.cellWidget(r,2).currentIndex()==0 else "unlock"} for r in range(self.table.rowCount())]
        self.schedule[self.day_cb.currentText()] = slots
        DataManager.save_json(DataManager.SCHEDULE_FILE, self.schedule)
        QMessageBox.information(self, "Bilgi", "Kaydedildi.")

    def copy_all(self):
        slots = [{"start": self.table.item(r,0).text(), "end": self.table.item(r,1).text(), "action": "lock" if self.table.cellWidget(r,2).currentIndex()==0 else "unlock"} for r in range(self.table.rowCount())]
        for d in self.schedule.keys(): self.schedule[d] = list(slots)
        DataManager.save_json(DataManager.SCHEDULE_FILE, self.schedule)
        QMessageBox.information(self, "Bilgi", "Haftalık program eşitlendi.")

    def check_bell_mode(self):
        now = datetime.now(); cur_t, cur_d = now.strftime("%H:%M"), ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][now.weekday()]
        for s in self.schedule.get(cur_d, []):
            if s["start"] <= cur_t <= s["end"]:
                for i in range(self.board_list.count()): self.execute_ssh(self.board_list.item(i).text(), s["action"])
                break

if __name__ == "__main__":
    app = QApplication(sys.argv); win = EtapKilitPaneli(); win.show(); sys.exit(app.exec())
