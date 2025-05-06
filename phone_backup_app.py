import sys
import subprocess
import os
import hashlib
import shutil
from tqdm import tqdm
from PIL import Image
from PIL.ExifTags import TAGS
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QLabel,
    QFrame, QMessageBox, QFileDialog, QInputDialog
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

# --- Config ---
DEVICE_DCIM_PATH = "/sdcard/DCIM/Camera"
HASH_LOG_FILE = "backup_log.txt"
CONFIG_FILE = "config.txt"
ADB_PATH = os.path.join("adb-tools", "adb.exe")

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
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            path = f.read().strip()
            if os.path.isdir(path):
                return path

    folder = QFileDialog.getExistingDirectory(None, "Select Backup Folder")
    if folder:
        os.makedirs(folder, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            f.write(folder)
        return folder
    else:
        show_message("Error", "Backup folder not selected. Exiting.")
        sys.exit()

def list_remote_files():
    result = subprocess.run([ADB_PATH, "shell", f"ls {DEVICE_DCIM_PATH}"], capture_output=True, text=True)
    return result.stdout.strip().splitlines()

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

def extract_photo_year(file_path):
    try:
        ext = file_path.lower().split('.')[-1]
        if ext in ("jpg", "jpeg"):
            image = Image.open(file_path)
            exif_data = image._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id)
                    if tag == 'DateTimeOriginal':
                        date_obj = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                        return str(date_obj.year)

        elif ext in ("mp4", "mov", "avi", "mkv"):
            parser = createParser(file_path)
            if not parser:
                return "Unknown"
            with parser:
                metadata = extractMetadata(parser)
                if metadata and metadata.has("creation_date"):
                    date_obj = metadata.get("creation_date")
                    return str(date_obj.year)

        return "Unknown"

    except Exception:
        return "Unknown"


def organize_by_year():
    backup_folder = get_backup_folder()
    for item in os.listdir(backup_folder):
        file_path = os.path.join(backup_folder, item)
        if os.path.isfile(file_path):
            year = extract_photo_year(file_path)
            if not year:
                year = "Unknown"
            dest_folder = os.path.join(backup_folder, year)
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
    backup_folder = get_backup_folder()
    for folder in os.listdir(backup_folder):
        folder_path = os.path.join(backup_folder, folder)
        if os.path.isdir(folder_path):
            for item in os.listdir(folder_path):
                src = os.path.join(folder_path, item)
                dst = os.path.join(backup_folder, item)
                if os.path.exists(dst):
                    base, ext = os.path.splitext(item)
                    count = 1
                    while True:
                        new_name = f"{base}_{count}{ext}"
                        dst = os.path.join(backup_folder, new_name)
                        if not os.path.exists(dst):
                            break
                        count += 1
                shutil.move(src, dst)
            os.rmdir(folder_path)

def delete_backed_up_files():
    existing_hashes = get_existing_hashes()
    temp_dir = "temp_verify"
    os.makedirs(temp_dir, exist_ok=True)

    deleted = 0
    for filename in list_remote_files():
        temp_path = os.path.join(temp_dir, filename)
        subprocess.run([ADB_PATH, "pull", f"{DEVICE_DCIM_PATH}/{filename}", temp_path], capture_output=True)
        if os.path.exists(temp_path):
            file_hash = calculate_hash(temp_path)
            if file_hash in existing_hashes:
                subprocess.run([ADB_PATH, "shell", f"rm {DEVICE_DCIM_PATH}/{filename}"])
                deleted += 1
            os.remove(temp_path)

    shutil.rmtree(temp_dir)
    return deleted

# --- GUI ---
class BackupApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📸 DCIM Backup Utility")
        self.setFixedSize(420, 420)
        self.setStyleSheet(self.load_styles())

        layout = QVBoxLayout()

        title = QLabel("📸 DCIM Photo Backup")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("margin-top: 10px;")

        self.backup_btn = QPushButton("📅 Backup Now")
        self.backup_btn.setMinimumHeight(45)
        self.backup_btn.clicked.connect(self.handle_backup)

        self.organize_btn = QPushButton("🗂️ Organize by Year")
        self.organize_btn.setMinimumHeight(45)
        self.organize_btn.clicked.connect(self.handle_organize)

        self.undo_btn = QPushButton("🔁 Undo Organization")
        self.undo_btn.setMinimumHeight(45)
        self.undo_btn.clicked.connect(self.handle_undo)

        self.delete_btn = QPushButton("🗑️ Delete from Phone")
        self.delete_btn.setMinimumHeight(45)
        self.delete_btn.clicked.connect(self.handle_delete)

        self.open_folder_btn = QPushButton("📂 Open Backup Folder")
        self.open_folder_btn.setMinimumHeight(45)
        self.open_folder_btn.clicked.connect(self.open_backup_folder)

        self.status_label = QLabel("✅ Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #666; font-size: 13px; padding: 6px;")

        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(self.backup_btn)
        layout.addWidget(self.organize_btn)
        layout.addWidget(self.undo_btn)
        layout.addWidget(self.delete_btn)
        layout.addWidget(self.open_folder_btn)
        layout.addWidget(QFrame(frameShape=QFrame.HLine))
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def handle_backup(self):
        if not phone_connected():
            QMessageBox.warning(self, "No Device", "No phone connected via USB or ADB is not enabled.")
            return
        count = perform_backup()
        backup_path = get_backup_folder()
        self.status_label.setText(f"🔄 {count} new photo(s) backed up.\n📁 Stored at: {backup_path}")


    def handle_organize(self):
        organize_by_year()
        backup_path = get_backup_folder()
        self.status_label.setText(f"🗂️ Photos organized by year.\n📁 Location: {backup_path}")


    def handle_undo(self):
        reply = QMessageBox.question(
            self,
            "Confirm Undo",
            "Are you sure you want to undo the organization?\nAll photos will be moved back to the main folder.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            undo_organization()
            backup_path = get_backup_folder()
            self.status_label.setText(f"🔁 Organization undone.\n📁 Photos moved to: {backup_path}")
        else:
            self.status_label.setText("❌ Undo canceled.")
    def open_backup_folder(self):
        folder_path = get_backup_folder()
        if os.path.exists(folder_path):
            if sys.platform == 'win32':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', folder_path])
            else:
                subprocess.run(['xdg-open', folder_path])



    def handle_delete(self):
        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            "⚠️ This will permanently delete backed-up photos from your phone.\n\nDo you want to proceed?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel
        )

        if confirm != QMessageBox.Yes:
            self.status_label.setText("❌ Deletion cancelled.")
            return

        text, ok = QInputDialog.getText(
            self,
            "Final Confirmation",
            "Type 'delete all' to confirm permanent deletion:"
        )

        if not ok or text.strip().lower() != "delete all":
            self.status_label.setText("❌ Deletion aborted. Confirmation text did not match.")
            return

        deleted = delete_backed_up_files()
        self.status_label.setText(f"🗑️ Deleted {deleted} photo(s) from phone.")

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
