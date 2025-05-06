import sys
import subprocess
import os
import hashlib
import shutil
from tqdm import tqdm
from PIL import Image
from PIL.ExifTags import TAGS
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QMessageBox
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

# --- Config ---
DEVICE_DCIM_PATH = "/sdcard/DCIM/Camera"
LOCAL_BACKUP_ROOT = "DCIM_Backups"
HASH_LOG_FILE = "backup_log.txt"
ADB_PATH = os.path.join("adb-tools", "adb.exe")  # Ensure adb.exe is in this folder

# --- Utility Functions ---

def show_message(title, message):
    QMessageBox.information(None, title, message)

def phone_connected():
    try:
        result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True)
        lines = result.stdout.strip().splitlines()
        return any("device" in line and not line.startswith("List") for line in lines)
    except Exception as e:
        show_message("Error", f"ADB Error: {str(e)}")
        return False

def get_existing_hashes():
    if not os.path.exists(HASH_LOG_FILE):
        return set()
    with open(HASH_LOG_FILE, "r") as f:
        return set(line.strip() for line in f.readlines())

def update_hash_log(new_hashes):
    with open(HASH_LOG_FILE, "a") as f:
        for h in new_hashes:
            f.write(h + "\n")

def calculate_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, "rb") as afile:
        while chunk := afile.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_backup_folder():
    os.makedirs(LOCAL_BACKUP_ROOT, exist_ok=True)
    return LOCAL_BACKUP_ROOT

def list_remote_files():
    result = subprocess.run([ADB_PATH, "shell", f"ls {DEVICE_DCIM_PATH}"], capture_output=True, text=True)
    return result.stdout.strip().splitlines()

def pull_file(filename, dest_folder):
    local_path = os.path.join(dest_folder, os.path.basename(filename))
    subprocess.run([ADB_PATH, "pull", f"{DEVICE_DCIM_PATH}/{filename}", local_path], capture_output=True)
    return local_path

# --- Backup Logic ---
def perform_backup():
    existing_hashes = get_existing_hashes()
    backup_folder = get_backup_folder()
    remote_files = list_remote_files()

    new_hashes = []
    new_files = []

    os.makedirs("temp_download", exist_ok=True)

    for filename in tqdm(remote_files, desc="Backing up"):
        temp_path = os.path.join("temp_download", filename)
        subprocess.run([ADB_PATH, "pull", f"{DEVICE_DCIM_PATH}/{filename}", temp_path], capture_output=True)

        if not os.path.exists(temp_path):
            continue

        file_hash = calculate_hash(temp_path)
        if file_hash not in existing_hashes:
            shutil.move(temp_path, os.path.join(backup_folder, filename))
            new_hashes.append(file_hash)
            new_files.append(filename)
        else:
            os.remove(temp_path)

    update_hash_log(new_hashes)
    shutil.rmtree("temp_download", ignore_errors=True)
    return len(new_files)

# --- Organize Logic ---
def extract_photo_year(file_path):
    try:
        if file_path.lower().endswith((".jpg", ".jpeg")):
            image = Image.open(file_path)
            exif_data = image._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id)
                    if tag == 'DateTimeOriginal':
                        date_obj = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                        return str(date_obj.year)
        # Fallback for videos and images without EXIF
        mod_time = os.path.getmtime(file_path)
        date_obj = datetime.fromtimestamp(mod_time)
        return str(date_obj.year)
    except Exception:
        return "Unknown"


def organize_by_year():
    for item in os.listdir(LOCAL_BACKUP_ROOT):
        file_path = os.path.join(LOCAL_BACKUP_ROOT, item)
        if os.path.isfile(file_path):
            year = extract_photo_year(file_path)
            if not year:
                year = "Unknown"
            dest_folder = os.path.join(LOCAL_BACKUP_ROOT, year)
            os.makedirs(dest_folder, exist_ok=True)

            new_path = os.path.join(dest_folder, item)
            if not os.path.exists(new_path):
                shutil.move(file_path, new_path)
            else:
                base, ext = os.path.splitext(item)
                count = 1
                while True:
                    new_name = f"{base}_{count}{ext}"
                    new_path = os.path.join(dest_folder, new_name)
                    if not os.path.exists(new_path):
                        shutil.move(file_path, new_path)
                        break
                    count += 1

def undo_organization():
    for folder in os.listdir(LOCAL_BACKUP_ROOT):
        folder_path = os.path.join(LOCAL_BACKUP_ROOT, folder)
        if os.path.isdir(folder_path):
            for item in os.listdir(folder_path):
                src = os.path.join(folder_path, item)
                dst = os.path.join(LOCAL_BACKUP_ROOT, item)
                if os.path.exists(dst):
                    base, ext = os.path.splitext(item)
                    count = 1
                    while True:
                        new_name = f"{base}_{count}{ext}"
                        dst = os.path.join(LOCAL_BACKUP_ROOT, new_name)
                        if not os.path.exists(dst):
                            break
                        count += 1
                shutil.move(src, dst)
            os.rmdir(folder_path)

# --- GUI ---
class BackupApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📸 DCIM Backup Utility")
        self.setFixedSize(420, 300)
        self.setStyleSheet(self.load_styles())

        layout = QVBoxLayout()

        title = QLabel("📸 DCIM Photo Backup")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("margin-top: 10px;")

        self.backup_btn = QPushButton("📥 Backup Now")
        self.backup_btn.setMinimumHeight(45)
        self.backup_btn.clicked.connect(self.handle_backup)

        self.organize_btn = QPushButton("🗂️ Organize by Year")
        self.organize_btn.setMinimumHeight(45)
        self.organize_btn.clicked.connect(self.handle_organize)

        self.undo_btn = QPushButton("🔁 Undo Organization")
        self.undo_btn.setMinimumHeight(45)
        self.undo_btn.clicked.connect(self.handle_undo)

        self.status_label = QLabel("✅ Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #666; font-size: 13px; padding: 6px;")

        layout.addWidget(title)
        layout.addSpacing(15)
        layout.addWidget(self.backup_btn)
        layout.addWidget(self.organize_btn)
        layout.addWidget(self.undo_btn)
        layout.addWidget(QFrame(frameShape=QFrame.HLine))
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def handle_backup(self):
        if not phone_connected():
            QMessageBox.warning(self, "No Device", "No phone connected via USB or ADB is not enabled.")
            return
        count = perform_backup()
        self.status_label.setText(f"🔄 {count} new photo(s) backed up.")

    def handle_organize(self):
        organize_by_year()
        self.status_label.setText("🔄 Photos organized by year!")

    def handle_undo(self):
        undo_organization()
        self.status_label.setText("🔄 Organization undone!")

    def load_styles(self):
        return """
        QWidget {
            background-color: #f2f4f7;
            font-family: 'Segoe UI', sans-serif;
            font-size: 14px;
        }
        QPushButton {
            background-color: #2e7d32;
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            transition: all 0.3s ease;
        }
        QPushButton:hover {
            background-color: #1b5e20;
        }
        QPushButton:pressed {
            background-color: #145a1c;
        }
        """

# --- Entry Point ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BackupApp()
    window.show()
    sys.exit(app.exec_())
