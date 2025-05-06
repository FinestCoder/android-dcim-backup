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
    QFrame, QMessageBox, QFileDialog, QInputDialog, QLineEdit,
    QHBoxLayout, QSpacerItem, QSizePolicy
)
from PyQt5.QtGui import QFont, QIcon, QPixmap, QColor, QPalette
from PyQt5.QtCore import Qt, QSize
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

# --- Config ---
DEVICE_DCIM_PATH = "/sdcard/DCIM/Camera"
HASH_LOG_FILE = "backup_log.txt"
CONFIG_FILE = "config.txt"
ADB_PATH = os.path.join("adb-tools", "adb.exe")

# --- Utility Functions ---
def show_message(title, message):
    msg = QMessageBox()
    msg.setWindowTitle(title)
    msg.setText(message)
    msg.setIcon(QMessageBox.Information)
    msg.setStyleSheet("""
        QMessageBox {
            background-color: #ffffff;
        }
        QLabel {
            color: #333333;
        }
    """)
    msg.exec_()

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
            base_path = f.read().strip()
            full_path = os.path.join(base_path, "DCIM_Backups")
            os.makedirs(full_path, exist_ok=True)
            return full_path

    base_folder = QFileDialog.getExistingDirectory(None, "Select Backup Folder")
    if base_folder:
        with open(CONFIG_FILE, "w") as f:
            f.write(base_folder)
        full_path = os.path.join(base_folder, "DCIM_Backups")
        os.makedirs(full_path, exist_ok=True)
        return full_path
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
        self.setMinimumSize(600, 600)
        self.setWindowIcon(QIcon(self.create_icon()))
        
        # Set modern palette
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(248, 249, 252))
        palette.setColor(QPalette.WindowText, QColor(53, 53, 53))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(248, 249, 252))
        palette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipText, QColor(248, 249, 252))
        palette.setColor(QPalette.Text, QColor(53, 53, 53))
        palette.setColor(QPalette.Button, QColor(255, 255, 255))
        palette.setColor(QPalette.ButtonText, QColor(0, 122, 217))
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Highlight, QColor(0, 122, 217))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        self.setPalette(palette)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QHBoxLayout()
        header.setSpacing(15)
        
        icon_label = QLabel()
        icon_pixmap = QPixmap(self.create_icon()).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(icon_pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        
        title = QLabel("DCIM Backup Utility")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("color: #333; margin: 0;")
        
        header.addWidget(icon_label)
        header.addWidget(title)
        header.addStretch()
        
        layout.addLayout(header)
        layout.addSpacing(10)

        # Add a subtle divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        divider.setStyleSheet("color: #e0e0e0;")
        layout.addWidget(divider)
        layout.addSpacing(15)

        # Buttons
        self.create_button("Backup Now", "backup_photo.png", "Backup photos from connected device", self.handle_backup, layout)
        self.create_button("Organize by Year", "organize.png", "Organize backed up photos by year", self.handle_organize, layout)
        self.create_button("Undo Organization", "undo.png", "Revert organization changes", self.handle_undo, layout)
        self.create_button("Delete from Phone", "delete.png", "Delete backed up photos from phone", self.handle_delete, layout)
        self.create_button("Open Backup Folder", "folder.png", "Open the backup folder", self.open_backup_folder, layout)
        self.create_button("Change Folder Path", "settings.png", "Change backup destination", self.handle_change_folder, layout)

        # Status bar
        self.status_label = QLabel("Ready to backup photos")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Segoe UI", 10))
        self.status_label.setStyleSheet("""
            QLabel {
                background-color: #f0f4f8;
                color: #4a5568;
                padding: 12px;
                border-radius: 6px;
                border: 1px solid #e2e8f0;
            }
        """)
        
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def create_button(self, text, icon_name, tooltip, callback, layout):
        btn = QPushButton(text)
        btn.setIcon(QIcon(f"icons/{icon_name}"))  # You'll need to provide these icons
        btn.setIconSize(QSize(24, 24))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        
        btn.setMinimumHeight(50)
        btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: #2d3748;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px 16px;
                text-align: left;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #f7fafc;
                border: 1px solid #cbd5e0;
            }
            QPushButton:pressed {
                background-color: #edf2f7;
            }
            QPushButton:focus {
                outline: none;
                border: 1px solid #4299e1;
            }
        """)
        
        layout.addWidget(btn)

    def create_icon(self):
        # Create a simple icon programmatically
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        
        from PyQt5.QtGui import QPainter, QBrush, QPen
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw camera body
        painter.setBrush(QBrush(QColor(0, 122, 217)))
        painter.setPen(QPen(QColor(0, 90, 180), 2))
        painter.drawEllipse(10, 10, 44, 44)
        
        # Draw lens
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(20, 20, 24, 24)
        
        # Draw flash
        painter.setBrush(QBrush(QColor(255, 204, 0)))
        painter.drawRect(40, 10, 10, 8)
        
        painter.end()
        return pixmap

    def handle_backup(self):
        if not phone_connected():
            msg = QMessageBox()
            msg.setWindowTitle("No Device")
            msg.setText("No phone connected via USB or ADB is not enabled.")
            msg.setIcon(QMessageBox.Warning)
            msg.setStyleSheet(self.get_messagebox_style())
            msg.exec_()
            return
            
        count = perform_backup()
        backup_path = get_backup_folder()
        self.status_label.setText(f"✓ {count} new photo(s) backed up\nLocation: {backup_path}")

    def handle_organize(self):
        organize_by_year()
        backup_path = get_backup_folder()
        self.status_label.setText(f"✓ Photos organized by year\nLocation: {backup_path}")

    def handle_undo(self):
        msg = QMessageBox()
        msg.setWindowTitle("Confirm Undo")
        msg.setText("Are you sure you want to undo the organization?\nAll photos will be moved back to the main folder.")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        msg.setStyleSheet(self.get_messagebox_style())
        
        reply = msg.exec_()
        if reply == QMessageBox.Yes:
            undo_organization()
            backup_path = get_backup_folder()
            self.status_label.setText(f"✓ Organization undone\nPhotos moved to: {backup_path}")
        else:
            self.status_label.setText("✗ Undo canceled")

    def open_backup_folder(self):
        folder_path = get_backup_folder()
        if os.path.exists(folder_path):
            if sys.platform == 'win32':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', folder_path])
            else:
                subprocess.run(['xdg-open', folder_path])

    def handle_change_folder(self):
        old_backup_folder = get_backup_folder()
        new_base_folder = QFileDialog.getExistingDirectory(self, "Select New Backup Folder")

        if not new_base_folder:
            self.status_label.setText("✗ Folder change cancelled")
            return

        new_backup_folder = os.path.join(new_base_folder, "DCIM_Backups")
        os.makedirs(new_backup_folder, exist_ok=True)

        old_files = [
            f for f in os.listdir(old_backup_folder)
            if os.path.isfile(os.path.join(old_backup_folder, f)) and f != "backup_log.txt"
        ]

        if old_files:
            dialog = QInputDialog()
            dialog.setWindowTitle("Move Existing Backups?")
            dialog.setLabelText("Photos exist in the previous backup folder.\n\nType 'move all and match' to move all to the new folder:")
            dialog.setTextValue("")
            dialog.setStyleSheet(self.get_messagebox_style())
            
            ok = dialog.exec_()
            text = dialog.textValue()
            
            if ok and text.strip().lower() == "move all and match":
                for file in old_files:
                    src = os.path.join(old_backup_folder, file)
                    dest = os.path.join(new_backup_folder, file)
                    if not os.path.exists(dest):
                        shutil.move(src, dest)
                    else:
                        base, ext = os.path.splitext(file)
                        count = 1
                        while True:
                            new_name = f"{base}_{count}{ext}"
                            new_dest = os.path.join(new_backup_folder, new_name)
                            if not os.path.exists(new_dest):
                                shutil.move(src, new_dest)
                                break
                            count += 1
                self.status_label.setText(f"✓ All files moved to: {new_backup_folder}")
            else:
                self.status_label.setText("✗ Move skipped. Old files remain in old folder.")

        # Update config
        with open(CONFIG_FILE, "w") as f:
            f.write(new_base_folder)

    def handle_delete(self):
        msg = QMessageBox()
        msg.setWindowTitle("Confirm Deletion")
        msg.setText("⚠️ This will permanently delete backed-up photos from your phone.\n\nDo you want to proceed?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        msg.setStyleSheet(self.get_messagebox_style())
        
        confirm = msg.exec_()
        if confirm != QMessageBox.Yes:
            self.status_label.setText("✗ Deletion cancelled")
            return

        dialog = QInputDialog()
        dialog.setWindowTitle("Final Confirmation")
        dialog.setLabelText("Type 'delete all' to confirm permanent deletion:")
        dialog.setTextValue("")
        dialog.setStyleSheet(self.get_messagebox_style())
        
        ok = dialog.exec_()
        text = dialog.textValue()

        if not ok or text.strip().lower() != "delete all":
            self.status_label.setText("✗ Deletion aborted. Confirmation text did not match.")
            return

        deleted = delete_backed_up_files()
        self.status_label.setText(f"✓ Deleted {deleted} photo(s) from phone")

    def get_messagebox_style(self):
        return """
        QMessageBox {
            background-color: #ffffff;
            font-family: 'Segoe UI', sans-serif;
        }
        QLabel {
            color: #333333;
            font-size: 14px;
        }
        QPushButton {
            background-color: #ffffff;
            color: #007ad9;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            padding: 6px 12px;
            min-width: 80px;
        }
        QPushButton:hover {
            background-color: #f0f0f0;
        }
        QPushButton:pressed {
            background-color: #e0e0e0;
        }
        """

# --- Entry Point ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set modern font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    # Set application style (Fusion is more modern than default)
    app.setStyle("Fusion")
    
    window = BackupApp()
    window.show()
    sys.exit(app.exec_())