import sys
import socket
import threading
import time
from datetime import datetime
from collections import deque
import os
import subprocess
import ctypes
from ctypes import wintypes
import json

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QPushButton, QSpinBox, QCheckBox, 
                           QTextEdit, QGroupBox, QFileDialog, QMessageBox, QFrame,
                           QGridLayout, QSizePolicy, QComboBox)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QPalette, QColor

# Try to import audio libraries in order of preference
try:
    from playsound3 import playsound
    HAS_AUDIO = True
    AUDIO_LIB = "playsound3"
except ImportError:
    try:
        import pygame
        HAS_AUDIO = True
        AUDIO_LIB = "pygame"
    except ImportError:
        HAS_AUDIO = False
        AUDIO_LIB = "none"

# Try to import pyqtgraph, make it optional
try:
    import pyqtgraph as pg
    import numpy as np
    HAS_PYQTGRAPH = True
    HAS_ENHANCED_GRAPHICS = True  # Both pyqtgraph and numpy available
except ImportError:
    try:
        import pyqtgraph as pg
        HAS_PYQTGRAPH = True
        HAS_ENHANCED_GRAPHICS = False  # Only pyqtgraph, no numpy
    except ImportError:
        HAS_PYQTGRAPH = False
        HAS_ENHANCED_GRAPHICS = False

class UserSettings:
    """Handle saving and loading user preferences"""
    
    def __init__(self, filename="monitor_settings.json"):
        self.filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        self.defaults = {
            "client_executable_path": "",
            "selected_sound": "gotime.mp3",
            "play_custom_sound": False,
            "notification_on_change": True,
            "notification_when_down": False,
            "auto_action_mode": "none",  # "none", "focus_existing", "launch_and_focus"
            "check_interval": 5,
            "enhanced_graphics": True,  # Enable fun graph effects
            "window_geometry": None  # [x, y, width, height]
        }
        self.settings = self.defaults.copy()
    
    def load(self):
        """Load settings from JSON file"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    # Merge with defaults to handle new settings in updates
                    self.settings = self.defaults.copy()
                    self.settings.update(loaded_settings)
        except Exception as e:
            print(f"Error loading settings: {e}, using defaults")
            self.settings = self.defaults.copy()
        
        return self.settings
    
    def save(self, settings_dict=None):
        """Save settings to JSON file"""
        if settings_dict:
            # Update internal settings with provided dict
            self.settings.update(settings_dict)
        
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def get(self, key, default=None):
        """Get a setting value"""
        return self.settings.get(key, default)
    
    def set(self, key, value):
        """Set a setting value and save immediately"""
        self.settings[key] = value
        self.save()
    
    def update_multiple(self, settings_dict):
        """Update multiple settings and save once"""
        self.settings.update(settings_dict)
        self.save()

class ServerMonitorThread(QThread):
    status_update = pyqtSignal(bool, float)  # is_up, check_duration
    
    def __init__(self, server, port, parent=None):
        super().__init__(parent)
        self.server = server
        self.port = port
        self.running = False
        self.check_interval = 5
        self._stop_event = threading.Event()  # For instant stop
        
    def run(self):
        while self.running and not self._stop_event.is_set():
            start_time = time.time()
            is_up = self.check_server()
            check_duration = time.time() - start_time
            
            self.status_update.emit(is_up, check_duration)
            
            # Calculate remaining sleep time
            remaining_sleep = max(0, self.check_interval - check_duration)
            
            # Use event.wait() instead of time.sleep() for instant stop
            if remaining_sleep > 0:
                self._stop_event.wait(remaining_sleep)
    
    def check_server(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.server, self.port))
            sock.close()
            return result == 0
        except:
            return False
    
    def set_interval(self, interval):
        self.check_interval = interval
    
    def stop(self):
        self.running = False
        self._stop_event.set()  # Signal immediate stop

class ServerMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server = "game.project-epoch.net"
        self.port = 3724
        
        # Initialize settings
        self.user_settings = UserSettings()
        settings = self.user_settings.load()
        
        # Apply loaded settings
        self.notification_on_change = settings["notification_on_change"]
        self.notification_when_down = settings["notification_when_down"]
        self.auto_action_mode = settings["auto_action_mode"]
        self.client_executable_path = settings["client_executable_path"]
        self.selected_sound = settings["selected_sound"]
        self.play_custom_sound = settings["play_custom_sound"]
        self.enhanced_graphics = settings["enhanced_graphics"]
        self.is_simulating = False
        
        # Audio resources path
        self.audio_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "audio")
        self.available_sounds = self.scan_audio_files()
        
        # Validate selected sound still exists
        if self.selected_sound not in self.available_sounds:
            self.selected_sound = "gotime.mp3" if "gotime.mp3" in self.available_sounds else "System Default"
        
        # Stats
        self.total_checks = 0
        self.successful_checks = 0
        self.start_time = None
        self.last_status = None
        self.max_log_lines = 50
        
        # History for graphs
        self.status_history = deque(maxlen=200)
        self.timestamps = deque(maxlen=200)
        self.uptime_data = deque(maxlen=200)
        
        # Monitoring thread
        self.monitor_thread = None
        
        self.init_ui()
        self.load_ui_settings()  # Apply settings to UI elements
        self.update_client_button_states()
    
    def load_ui_settings(self):
        """Apply loaded settings to UI elements"""
        # Set spinbox value
        settings = self.user_settings.settings
        self.delay_spinbox.setValue(settings["check_interval"])
        
        # Set checkboxes
        self.notify_change_cb.setChecked(self.notification_on_change)
        self.notify_down_cb.setChecked(self.notification_when_down)
        self.play_sound_cb.setChecked(self.play_custom_sound)
        
        # Set sound dropdown
        if self.selected_sound in self.available_sounds:
            self.sound_combo.setCurrentText(self.selected_sound)
        
        # Set auto-action checkboxes
        self.update_auto_action_checkboxes()
        
        # Set enhanced graphics checkbox if it exists
        if hasattr(self, 'enhanced_graphics_cb'):
            self.enhanced_graphics_cb.setChecked(self.enhanced_graphics)
        
        # Set client path if exists
        if self.client_executable_path and os.path.exists(self.client_executable_path):
            filename = os.path.basename(self.client_executable_path)
            self.client_path_label.setText(f"Client: {filename}")
            self.client_path_label.setStyleSheet("color: #66bb6a; font-weight: bold; font-size: 11px;")
        
        # Restore window geometry if saved
        geometry = settings.get("window_geometry")
        if geometry and len(geometry) == 4:
            self.setGeometry(geometry[0], geometry[1], geometry[2], geometry[3])
    
    def save_current_settings(self):
        """Save current UI state to settings"""
        current_settings = {
            "client_executable_path": self.client_executable_path,
            "selected_sound": self.selected_sound,
            "play_custom_sound": self.play_custom_sound,
            "notification_on_change": self.notification_on_change,
            "notification_when_down": self.notification_when_down,
            "auto_action_mode": self.auto_action_mode,
            "check_interval": self.delay_spinbox.value(),
            "enhanced_graphics": self.enhanced_graphics,
            "window_geometry": [self.x(), self.y(), self.width(), self.height()]
        }
        self.user_settings.update_multiple(current_settings)
    
    def closeEvent(self, event):
        """Handle window close event - save settings"""
        self.save_current_settings()
        if self.monitor_thread and self.monitor_thread.running:
            self.monitor_thread.stop()
            self.monitor_thread.wait()
        event.accept()

    def get_resource_path(self):
        """Get the correct path for resources, works with both script and executable"""
        if getattr(sys, 'frozen', False):
            # Running as executable - resources are in the same directory as the .exe
            application_path = os.path.dirname(sys.executable)
        else:
            # Running as script - resources are relative to the script
            application_path = os.path.dirname(os.path.abspath(__file__))
        
        return application_path
        
    def scan_audio_files(self):
        """Scan resources/audio folder for MP3 files"""
        sounds = []
        
        # Try multiple possible locations for audio files
        possible_paths = [
            # When running as executable, resources folder is next to the .exe
            os.path.join(self.get_resource_path(), "resources", "audio"),
            # Alternative: audio folder directly next to executable  
            os.path.join(self.get_resource_path(), "audio"),
            # When running as script
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "audio")
        ]
        
        audio_path_found = None
        
        for path in possible_paths:
            if os.path.exists(path):
                audio_path_found = path
                break
        
        if audio_path_found:
            self.audio_path = audio_path_found  # Update the instance variable
            try:
                for file in os.listdir(audio_path_found):
                    if file.lower().endswith(('.mp3', '.wav', '.ogg')):
                        sounds.append(file)
                sounds.sort()  # Alphabetical order
                print(f"Found audio files in: {audio_path_found}")
                print(f"Audio files found: {sounds}")
            except Exception as e:
                print(f"Error scanning audio folder: {e}")
        else:
            print("No audio folder found in any expected location")
            print(f"Searched paths: {possible_paths}")
        
        # Always include system default option
        sounds.insert(0, "System Default")
        return sounds
    
    def get_sound_path(self, sound_name):
        """Get full path for a sound file"""
        if sound_name == "System Default":
            return None
        return os.path.join(self.audio_path, sound_name)
        
    def init_ui(self):
        self.setWindowTitle("Project Epoch Server Monitor")
        self.setGeometry(100, 100, 600, 750)  # More compact size
        
        # Set dark theme with more compact styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 6px;
                background-color: #353535;
                margin-bottom: 4px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #ffffff;
                font-size: 12px;
            }
            QPushButton {
                background-color: #404040;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                color: #ffffff;
                font-weight: bold;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #505050;
                border-color: #666666;
            }
            QPushButton:pressed {
                background-color: #333333;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                border-color: #444444;
                color: #666666;
            }
            QSpinBox {
                background-color: #404040;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                color: #ffffff;
                min-width: 80px;
                min-height: 20px;
            }
            QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #555555;
                border-left-style: solid;
                border-top-right-radius: 3px;
                background-color: #404040;
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #555555;
                border-left-style: solid;
                border-bottom-right-radius: 3px;
                background-color: #404040;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #505050;
            }
            QSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 4px solid #ffffff;
                width: 0px;
                height: 0px;
            }
            QSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #ffffff;
                width: 0px;
                height: 0px;
            }
            QCheckBox {
                color: #ffffff;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #404040;
                border: 1px solid #555555;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border: 1px solid #0078d4;
                border-radius: 2px;
            }
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #555555;
                border-radius: 4px;
                color: #ffffff;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }
            QLabel {
                color: #ffffff;
            }
        """)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(6)  # Reduce spacing between elements
        layout.setContentsMargins(8, 8, 8, 8)  # Reduce margins
        
        # Compact server info and settings combined
        top_group = QGroupBox("Server & Settings")
        top_layout = QGridLayout(top_group)
        top_layout.setContentsMargins(8, 12, 8, 8)
        
        # Server info
        top_layout.addWidget(QLabel("Server:"), 0, 0)
        server_label = QLabel(f"{self.server}:{self.port}")
        server_label.setStyleSheet("color: #64b5f6; font-weight: bold;")
        top_layout.addWidget(server_label, 0, 1)
        
        # Check interval
        top_layout.addWidget(QLabel("Check every:"), 1, 0)
        interval_layout = QHBoxLayout()
        self.delay_spinbox = QSpinBox()
        self.delay_spinbox.setRange(2, 300)
        self.delay_spinbox.setValue(5)
        self.delay_spinbox.setSuffix(" seconds")
        self.delay_spinbox.valueChanged.connect(self.on_delay_changed)
        interval_layout.addWidget(self.delay_spinbox)
        interval_layout.addStretch()
        top_layout.addLayout(interval_layout, 1, 1)
        layout.addWidget(top_group)
        
        # Status section - more compact
        status_group = QGroupBox("Server Status")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(8, 12, 8, 8)
        status_layout.setSpacing(4)
        
        # Current status row
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self.status_label = QLabel("STOPPED")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffab40;")
        status_row.addWidget(self.status_label)
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #757575; font-size: 16px;")
        status_row.addWidget(self.status_indicator)
        status_row.addStretch()
        status_layout.addLayout(status_row)
        
        # Statistics in compact grid
        stats_layout = QGridLayout()
        stats_layout.setSpacing(4)
        self.total_checks_label = QLabel("Total Checks: 0")
        self.uptime_label = QLabel("Uptime: 0.0%")
        self.runtime_label = QLabel("Runtime: 00:00:00")
        stats_layout.addWidget(self.total_checks_label, 0, 0)
        stats_layout.addWidget(self.uptime_label, 0, 1)
        stats_layout.addWidget(self.runtime_label, 0, 2)
        status_layout.addLayout(stats_layout)
        layout.addWidget(status_group)
        
        # All controls in one compact group
        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setContentsMargins(8, 12, 8, 8)
        controls_layout.setSpacing(6)
        
        # Monitor control row
        monitor_row = QHBoxLayout()
        monitor_row.addWidget(QLabel("Monitor:"))
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_monitoring)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_monitoring)
        self.stop_btn.setEnabled(False)
        monitor_row.addWidget(self.start_btn)
        monitor_row.addWidget(self.stop_btn)
        monitor_row.addStretch()
        controls_layout.addLayout(monitor_row)
        
        # Client control row
        client_row = QHBoxLayout()
        client_row.addWidget(QLabel("Client:"))
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self.browse_executable)
        self.test_launch_btn = QPushButton("Test Launch")
        self.test_launch_btn.clicked.connect(self.test_launch_client)
        self.test_focus_btn = QPushButton("Test Focus")
        self.test_focus_btn.clicked.connect(self.test_focus_client)
        client_row.addWidget(self.browse_btn)
        client_row.addWidget(self.test_launch_btn)
        client_row.addWidget(self.test_focus_btn)
        client_row.addStretch()
        controls_layout.addLayout(client_row)
        
        # Client path label
        self.client_path_label = QLabel("Click 'Browse' to select game executable")
        self.client_path_label.setStyleSheet("color: #999999; font-style: italic; font-size: 11px;")
        controls_layout.addWidget(self.client_path_label)
        
        # Data management row
        data_row = QHBoxLayout()
        data_row.addWidget(QLabel("Data:"))
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.clicked.connect(self.clear_log)
        clear_history_btn = QPushButton("Clear History")
        clear_history_btn.clicked.connect(self.clear_history)
        data_row.addWidget(clear_log_btn)
        data_row.addWidget(clear_history_btn)
        data_row.addStretch()
        controls_layout.addLayout(data_row)
        layout.addWidget(controls_group)
        
        # Compact settings
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setContentsMargins(8, 12, 8, 8)
        settings_layout.setSpacing(2)
        
        # Notifications with test button and sound
        notif_row = QHBoxLayout()
        notif_row.addWidget(QLabel("Notifications:"))
        test_notif_btn = QPushButton("Test")
        test_notif_btn.clicked.connect(self.test_notification)
        notif_row.addWidget(test_notif_btn)
        notif_row.addStretch()
        settings_layout.addLayout(notif_row)
        
        self.notify_change_cb = QCheckBox("Notify on status change")
        self.notify_change_cb.setChecked(True)
        self.notify_change_cb.toggled.connect(self.toggle_change_notifications)
        self.notify_down_cb = QCheckBox("Notify while server is down")
        self.notify_down_cb.toggled.connect(self.toggle_down_notifications)
        settings_layout.addWidget(self.notify_change_cb)
        settings_layout.addWidget(self.notify_down_cb)
        
        # Sound settings
        sound_row = QHBoxLayout()
        sound_row.addWidget(QLabel("Sound:"))
        
        # Sound dropdown
        self.sound_combo = QComboBox()
        self.sound_combo.addItems(self.available_sounds)
        # Set default to gotime.mp3 if available, otherwise System Default
        if "gotime.mp3" in self.available_sounds:
            self.sound_combo.setCurrentText("gotime.mp3")
            self.selected_sound = "gotime.mp3"
        else:
            self.sound_combo.setCurrentText("System Default")
            self.selected_sound = "System Default"
        self.sound_combo.currentTextChanged.connect(self.on_sound_changed)
        
        self.test_sound_btn = QPushButton("Test Sound")
        self.test_sound_btn.clicked.connect(self.test_sound)
        
        sound_row.addWidget(self.sound_combo)
        sound_row.addWidget(self.test_sound_btn)
        sound_row.addStretch()
        settings_layout.addLayout(sound_row)
        
        self.play_sound_cb = QCheckBox("Play sound with notifications")
        self.play_sound_cb.toggled.connect(self.toggle_sound_notifications)
        settings_layout.addWidget(self.play_sound_cb)
        
        # Show audio library availability and disable if needed
        if not HAS_AUDIO:
            audio_info = QLabel("🎵 For custom sounds, install: pip install playsound3")
            audio_info.setStyleSheet("color: #ff9800; font-style: italic; padding: 2px;")
            settings_layout.addWidget(audio_info)
            
            # Disable sound-related controls if no audio library and custom sounds exist
            if len(self.available_sounds) > 1:  # More than just "System Default"
                self.sound_combo.setEnabled(False)
                self.test_sound_btn.setEnabled(False)
                self.play_sound_cb.setEnabled(False)
        else:
            # Show audio folder info and library used
            if len(self.available_sounds) > 1:
                folder_info = QLabel(f"📁 Audio files from: resources/audio/ ({len(self.available_sounds)-1} files)")
                folder_info.setStyleSheet("color: #66bb6a; font-size: 10px; padding: 2px;")
                settings_layout.addWidget(folder_info)
        
        # Auto-actions - much clearer options
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #555555;")
        settings_layout.addWidget(separator)
        
        auto_label = QLabel("When server comes UP:")
        auto_label.setStyleSheet("font-weight: bold; color: #cccccc; font-size: 11px;")
        settings_layout.addWidget(auto_label)
        
        # Radio button style behavior with clear descriptions
        self.no_action_cb = QCheckBox("Do nothing")
        self.no_action_cb.setChecked(True)  # Default
        self.no_action_cb.toggled.connect(self.toggle_no_action)
        
        self.focus_existing_cb = QCheckBox("Find and focus Project Epoch window")
        self.focus_existing_cb.toggled.connect(self.toggle_focus_existing)
        
        self.launch_and_focus_cb = QCheckBox("Launch selected client then focus it")
        self.launch_and_focus_cb.toggled.connect(self.toggle_launch_and_focus)
        
        settings_layout.addWidget(self.no_action_cb)
        settings_layout.addWidget(self.focus_existing_cb)
        settings_layout.addWidget(self.launch_and_focus_cb)
        
        # Add helpful text
        help_text = QLabel("Note: 'Find and focus' does the same as 'Test Focus' button")
        help_text.setStyleSheet("color: #888888; font-style: italic; font-size: 10px;")
        settings_layout.addWidget(help_text)
        layout.addWidget(settings_group)
        
        # Graph section (only if pyqtgraph is available)
        if HAS_PYQTGRAPH:
            self.create_graph_section(layout)
        else:
            # Show a message about optional graph
            graph_info = QLabel("📊 Install 'pyqtgraph' for uptime graph: pip install pyqtgraph")
            graph_info.setStyleSheet("color: #888888; font-style: italic; padding: 4px;")
            layout.addWidget(graph_info)
        
        # Activity log - more compact
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(8, 12, 8, 8)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(120)  # Smaller log area
        self.log_text.setPlainText("Monitor not started yet...")
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)
        
        # Timer for UI updates
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_runtime_display)
    
    def create_graph_section(self, layout):
        """Create graph section with optional enhanced effects"""
        graph_group = QGroupBox("Uptime Graph")
        graph_layout = QVBoxLayout(graph_group)
        graph_layout.setContentsMargins(8, 12, 8, 8)
        
        # Graph options and simulation row
        options_row = QHBoxLayout()
        
        # Graphics options (if enhanced graphics available)
        if HAS_ENHANCED_GRAPHICS:
            options_row.addWidget(QLabel("Graphics:"))
            
            self.enhanced_graphics_cb = QCheckBox("Enhanced effects")
            self.enhanced_graphics_cb.setChecked(self.enhanced_graphics)
            self.enhanced_graphics_cb.toggled.connect(self.toggle_enhanced_graphics)
            options_row.addWidget(self.enhanced_graphics_cb)
            
            # Add separator
            separator = QLabel(" | ")
            separator.setStyleSheet("color: #666666;")
            options_row.addWidget(separator)
        
        # Simulation controls
        options_row.addWidget(QLabel("Test:"))
        
        self.simulate_btn = QPushButton("Simulate UP")
        self.simulate_btn.clicked.connect(self.simulate_server_up)
        self.simulate_btn.setStyleSheet("background-color: #4caf50; color: white; padding: 4px 8px; font-size: 10px;")
        self.simulate_btn.setToolTip("Test enhanced effects by simulating server coming online")
        options_row.addWidget(self.simulate_btn)
        
        self.reset_simulation_btn = QPushButton("Reset")
        self.reset_simulation_btn.clicked.connect(self.reset_simulation)
        self.reset_simulation_btn.setStyleSheet("background-color: #ff5722; color: white; padding: 4px 8px; font-size: 10px;")
        self.reset_simulation_btn.setToolTip("Clear simulation data and reset graph")
        self.reset_simulation_btn.setEnabled(False)  # Initially disabled
        options_row.addWidget(self.reset_simulation_btn)
        
        options_row.addStretch()
        graph_layout.addLayout(options_row)
        
        # Create appropriate graph widget
        from enhanced_graph import create_graph_widget  # Import the new module
        self.plot_widget = create_graph_widget(self, enhanced=self.enhanced_graphics)
        
        # Store reference to old update method if we're using standard widget
        if hasattr(self.plot_widget, 'plot') and not hasattr(self.plot_widget, 'update_with_effects'):
            # Standard pyqtgraph widget - add simple line
            self.uptime_line = self.plot_widget.plot([], [], pen=pg.mkPen(color='#66bb6a', width=2))
        
        graph_layout.addWidget(self.plot_widget)
        layout.addWidget(graph_group)
    
    def update_graph(self):
        """Update the uptime graph with optional enhanced effects"""
        if not hasattr(self, 'plot_widget'):
            return
            
        # Determine if status changed
        current_status = len(self.status_history) > 0 and self.status_history[-1] == 1
        status_changed = (self.last_status is not None and 
                        len(self.status_history) > 0 and 
                        current_status != self.last_status)
        
        if hasattr(self.plot_widget, 'update_with_effects'):
            # Enhanced graph widget
            self.plot_widget.update_with_effects(
                self.uptime_data, 
                status_changed=status_changed, 
                is_up=current_status
            )
        elif hasattr(self.plot_widget, 'plot') and hasattr(self, 'uptime_line'):
            # Standard pyqtgraph widget
            if len(self.uptime_data) > 1:
                x_data = list(range(len(self.uptime_data)))
                y_data = list(self.uptime_data)
                self.uptime_line.setData(x_data, y_data)
        # If neither, it's the fallback widget - no action needed

    def toggle_enhanced_graphics(self, checked):
        """Toggle enhanced graphics and recreate graph widget"""
        self.enhanced_graphics = checked
        self.user_settings.set("enhanced_graphics", checked)
        
        # Find and replace the graph widget
        if hasattr(self, 'plot_widget'):
            # Store current data
            current_uptime_data = list(self.uptime_data) if self.uptime_data else []
            
            # Remove old widget
            old_widget = self.plot_widget
            parent_layout = old_widget.parent().layout()
            parent_layout.removeWidget(old_widget)
            old_widget.deleteLater()
            
            # Create new widget with updated setting
            from enhanced_graph import create_graph_widget
            self.plot_widget = create_graph_widget(self, enhanced=self.enhanced_graphics)
            
            # Add back to layout
            parent_layout.addWidget(self.plot_widget)
            
            # Setup line reference if needed
            if hasattr(self.plot_widget, 'plot') and not hasattr(self.plot_widget, 'update_with_effects'):
                self.uptime_line = self.plot_widget.plot([], [], pen=pg.mkPen(color='#66bb6a', width=2))
            
            # Restore data
            if current_uptime_data:
                self.uptime_data = deque(current_uptime_data, maxlen=200)
                self.update_graph()
            
            # Log the change
            mode = "enhanced" if checked else "standard"
            self.add_to_log(f"Switched to {mode} graph mode")

    def simulate_server_up(self):
        """Simulate server coming UP for testing effects"""
        if not hasattr(self, 'plot_widget'):
            self.add_to_log("No graph widget available for simulation")
            return
        
        # Mark that we're in simulation mode
        self.is_simulating = True
        
        # Add some fake data points if we don't have any
        if len(self.uptime_data) == 0:
            # Add some "down" history first
            for i in range(10):
                self.status_history.append(0)
                self.timestamps.append(f"SIM-{i:02d}")
                self.uptime_data.append(0.0)
        
        # Simulate server coming UP
        self.status_history.append(1)
        current_time = datetime.now().strftime("%H:%M:%S")
        self.timestamps.append(current_time)
        
        # Calculate new uptime (should jump up)
        successful_checks = sum(self.status_history)
        uptime_percent = (successful_checks / len(self.status_history)) * 100
        self.uptime_data.append(uptime_percent)
        
        # Update stats display
        self.total_checks_label.setText(f"Total Checks: {len(self.status_history)} (simulated)")
        self.uptime_label.setText(f"Uptime: {uptime_percent:.1f}%")
        
        # Trigger enhanced effects by simulating status change
        if hasattr(self.plot_widget, 'update_with_effects'):
            # Enhanced graph widget - trigger celebration!
            self.plot_widget.update_with_effects(
                self.uptime_data, 
                status_changed=True,  # Force status change
                is_up=True           # Server is UP!
            )
            self.add_to_log(f"[{current_time}] ✨ SIMULATED: Server UP! ✨")
        elif hasattr(self.plot_widget, 'plot') and hasattr(self, 'uptime_line'):
            # Standard graph widget
            x_data = list(range(len(self.uptime_data)))
            y_data = list(self.uptime_data)
            self.uptime_line.setData(x_data, y_data)
            self.add_to_log(f"[{current_time}] SIMULATED: Server UP (standard graph mode)")
        else:
            self.add_to_log(f"[{current_time}] SIMULATED: Server UP (basic widget mode)")
        
        # Enable reset button and disable simulate
        self.simulate_btn.setEnabled(False)
        self.reset_simulation_btn.setEnabled(True)

    def reset_simulation(self):
        """Reset simulation data and clear graph"""
        # Clear all data
        self.status_history.clear()
        self.timestamps.clear()
        self.uptime_data.clear()
        
        # Reset stats
        self.total_checks_label.setText("Total Checks: 0")
        self.uptime_label.setText("Uptime: 0.0%")
        
        # Clear graph based on widget type
        if hasattr(self.plot_widget, 'clear_graph'):
            # Enhanced widget
            self.plot_widget.clear_graph()
        elif hasattr(self, 'uptime_line'):
            # Standard widget
            self.uptime_line.setData([], [])
        
        # Reset simulation state
        self.is_simulating = False
        
        # Reset button states
        self.simulate_btn.setEnabled(True)
        self.reset_simulation_btn.setEnabled(False)
        
        self.add_to_log("Simulation reset - graph cleared!")
        
    def update_client_button_states(self):
        """Update button states based on whether client is selected"""
        has_client = bool(self.client_executable_path)
        self.test_launch_btn.setEnabled(has_client)
        
        # Update auto-action availability
        if hasattr(self, 'launch_and_focus_cb'):  # Only if UI is created
            if not has_client and self.auto_action_mode == "launch_and_focus":
                # Reset to focus existing if no client selected
                self.auto_action_mode = "focus_existing"
                self.update_auto_action_checkboxes()
            
            # Enable/disable launch option based on client selection
            self.launch_and_focus_cb.setEnabled(has_client)
            if not has_client:
                self.launch_and_focus_cb.setStyleSheet("color: #666666;")
            else:
                self.launch_and_focus_cb.setStyleSheet("color: #ffffff;")
    
    def update_sound_button_states(self):
        """Update sound button states based on audio library availability"""
        if not HAS_AUDIO and self.selected_sound != "System Default":
            self.test_sound_btn.setEnabled(False)
        else:
            self.test_sound_btn.setEnabled(True)
    
    def on_sound_changed(self, sound_name):
        """Handle sound selection change"""
        self.selected_sound = sound_name
        self.update_sound_button_states()
        self.add_to_log(f"Sound changed to: {sound_name}")
        # Save setting immediately
        self.user_settings.set("selected_sound", sound_name)
    
    def play_system_sound(self):
        """Play system notification sound"""
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)  # Fixed constant
            elif sys.platform == "darwin":  # macOS
                os.system("afplay /System/Library/Sounds/Glass.aiff")
            else:  # Linux
                os.system("paplay /usr/share/sounds/alsa/Front_Left.wav 2>/dev/null || echo -e '\a'")
        except Exception as e:
            print(f"System sound error: {e}")
    
    def play_custom_sound_file(self, sound_path):
        """Play custom sound file using available audio library"""
        if AUDIO_LIB == "playsound3":
            playsound(sound_path)
        elif AUDIO_LIB == "pygame":
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
    
    def play_sound(self):
        """Play notification sound"""
        if not self.play_custom_sound:
            return
            
        sound_path = self.get_sound_path(self.selected_sound)
        
        if sound_path and os.path.exists(sound_path) and HAS_AUDIO:
            # Play custom sound
            try:
                threading.Thread(target=lambda: self.play_custom_sound_file(sound_path), daemon=True).start()
            except Exception as e:
                print(f"Custom sound error: {e}")
                self.play_system_sound()  # Fallback
        else:
            # Play system notification sound
            self.play_system_sound()
    
    def test_sound(self):
        """Test playing the selected sound"""
        sound_path = self.get_sound_path(self.selected_sound)
        
        if sound_path and os.path.exists(sound_path):
            if not HAS_AUDIO:
                self.add_to_log("Error: Audio library required for custom sounds")
                return
                
            try:
                threading.Thread(target=lambda: self.play_custom_sound_file(sound_path), daemon=True).start()
                self.add_to_log(f"Playing: {self.selected_sound} (using {AUDIO_LIB})")
            except Exception as e:
                self.add_to_log(f"Error playing {self.selected_sound}: {e}")
        else:
            # Test system sound
            try:
                self.play_system_sound()
                self.add_to_log("Playing system notification sound")
            except Exception as e:
                self.add_to_log(f"Error playing system sound: {e}")
    
    def test_notification(self):
        """Test showing a notification with sound"""
        self.show_notification("Test Notification", "This is a test notification from Project Epoch Monitor!")
        self.add_to_log("Test notification sent")
    
    def update_auto_action_checkboxes(self):
        """Update checkbox states based on current mode"""
        self.no_action_cb.setChecked(self.auto_action_mode == "none")
        self.focus_existing_cb.setChecked(self.auto_action_mode == "focus_existing")
        self.launch_and_focus_cb.setChecked(self.auto_action_mode == "launch_and_focus")
        
    def browse_executable(self):
        """Open file dialog to select client executable"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Client Executable",
            "",
            "Executable files (*.exe);;All files (*.*)"
        )
        
        if file_path:
            self.client_executable_path = file_path
            filename = os.path.basename(file_path)
            self.client_path_label.setText(f"Client: {filename}")
            self.client_path_label.setStyleSheet("color: #66bb6a; font-weight: bold; font-size: 11px;")
            self.update_client_button_states()
            self.add_to_log(f"Client executable set: {filename}")
            # Save setting immediately
            self.user_settings.set("client_executable_path", file_path)
    
    def launch_client(self):
        """Launch the selected client executable"""
        if not self.client_executable_path:
            self.add_to_log("No client executable selected!")
            return False
        
        if not os.path.exists(self.client_executable_path):
            self.add_to_log("Selected executable not found!")
            return False
        
        try:
            subprocess.Popen([self.client_executable_path])
            filename = os.path.basename(self.client_executable_path)
            self.add_to_log(f"Launched: {filename}")
            return True
        except Exception as e:
            self.add_to_log(f"Error launching client: {e}")
            return False
    
    def test_launch_client(self):
        """Test launching client"""
        self.launch_client()
    
    def bring_client_to_front(self):
        """Bring client window to front"""
        try:
            user32 = ctypes.windll.user32
            found_window = False
            
            def enum_windows_proc(hwnd, lParam):
                nonlocal found_window
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buffer, length + 1)
                        window_title = buffer.value
                        
                        # Exclude Discord and other apps
                        excluded_keywords = ["Monitor", "Chrome", "Firefox", "Edge", "Browser", "Discord"]
                        if any(keyword.lower() in window_title.lower() for keyword in excluded_keywords):
                            return True
                        
                        # Look for game windows
                        wow_keywords = ["World of Warcraft"]
                        
                        # For Project Epoch, be more specific
                        if "project epoch" in window_title.lower():
                            if not any(excluded.lower() in window_title.lower() for excluded in ["discord", "chrome", "firefox", "edge", "browser"]):
                                wow_keywords.append("Project Epoch")
                        
                        # Add executable name if selected
                        if self.client_executable_path:
                            exe_name = os.path.splitext(os.path.basename(self.client_executable_path))[0]
                            wow_keywords.append(exe_name)
                        
                        if any(keyword.lower() in window_title.lower() for keyword in wow_keywords):
                            try:
                                user32.SetForegroundWindow(hwnd)
                                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                                user32.SetActiveWindow(hwnd)
                                found_window = True
                                self.add_to_log(f"Activated: {window_title}")
                                return False
                            except:
                                pass
                return True
            
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
            
            if not found_window:
                self.add_to_log("No client windows detected")
            
            return found_window
            
        except Exception as e:
            self.add_to_log(f"Error bringing client to front: {e}")
            return False
    
    def test_focus_client(self):
        """Test focusing client window"""
        self.bring_client_to_front()
    
    def on_delay_changed(self, value):
        """Handle delay change"""
        if self.monitor_thread and self.monitor_thread.running:
            self.monitor_thread.set_interval(value)
        # Save setting immediately
        self.user_settings.set("check_interval", value)
    
    def start_monitoring(self):
        """Start monitoring"""
        if not self.monitor_thread or not self.monitor_thread.running:
            # Clear any simulation data before starting real monitoring
            if self.is_simulating:
                self.reset_simulation()
            
            self.monitor_thread = ServerMonitorThread(self.server, self.port)
            self.monitor_thread.set_interval(self.delay_spinbox.value())
            self.monitor_thread.status_update.connect(self.on_status_update)
            self.monitor_thread.running = True
            self.monitor_thread.start()
            
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.simulate_btn.setEnabled(False)  # Disable simulate while monitoring
            self.reset_simulation_btn.setEnabled(False)  # Disable reset while monitoring
            self.start_time = datetime.now()
            
            self.ui_timer.start(1000)  # Update every second
            self.add_to_log("Starting monitor...")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.monitor_thread.wait()
            
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        # Only enable simulate if we're not in simulation mode
        self.simulate_btn.setEnabled(not self.is_simulating)
        # Only enable reset if we ARE in simulation mode
        self.reset_simulation_btn.setEnabled(self.is_simulating)
        self.ui_timer.stop()
        
        self.status_label.setText("STOPPED")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffab40;")
        self.status_indicator.setStyleSheet("color: #757575; font-size: 16px;")
    
    def on_status_update(self, is_up, check_duration):
        """Handle status update from monitoring thread"""
        self.total_checks += 1
        if is_up:
            self.successful_checks += 1
        
        # Update UI
        status_text = "ONLINE" if is_up else "OFFLINE"
        color = "#66bb6a" if is_up else "#f44336"
        
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {color};")
        self.status_indicator.setStyleSheet(f"color: {color}; font-size: 16px;")
        
        # Update stats
        uptime_percent = (self.successful_checks / self.total_checks) * 100
        self.total_checks_label.setText(f"Total Checks: {self.total_checks}")
        self.uptime_label.setText(f"Uptime: {uptime_percent:.1f}%")
        
        # Add to history
        self.status_history.append(1 if is_up else 0)
        self.timestamps.append(datetime.now().strftime("%H:%M:%S"))
        self.uptime_data.append(uptime_percent)
        
        # Update graph if available
        self.update_graph()
        
        # Log entry
        current_time = datetime.now().strftime("%H:%M:%S")
        interval = self.delay_spinbox.value()
        log_entry = f"[{current_time}] {status_text}"
        self.add_to_log(log_entry)
        
        # Handle notifications and actions
        state_changed = (self.last_status is not None and is_up != self.last_status)
        
        if (self.notification_on_change and state_changed) or (self.notification_when_down and not is_up):
            status_word = "UP" if is_up else "DOWN"
            self.show_notification(f"Epoch is {status_word}", 
                                 f"Port {self.port} on {self.server} @ {current_time}")
        
        # Handle client actions when server comes UP
        if state_changed and is_up:
            if self.auto_action_mode == "launch_and_focus":
                self.launch_client()
                QTimer.singleShot(2000, self.bring_client_to_front)  # Delay before focus
            elif self.auto_action_mode == "focus_existing":
                self.bring_client_to_front()
        
        self.last_status = is_up
    
    def update_runtime_display(self):
        """Update runtime display"""
        if self.start_time:
            runtime = datetime.now() - self.start_time
            runtime_str = str(runtime).split('.')[0]
            self.runtime_label.setText(f"Runtime: {runtime_str}")
    
    def add_to_log(self, message):
        """Add message to log"""
        current_log = self.log_text.toPlainText()
        log_lines = current_log.split('\n') if current_log.strip() else []
        
        log_lines.append(message)
        
        if len(log_lines) > self.max_log_lines:
            log_lines = log_lines[-self.max_log_lines:]
        
        new_log = '\n'.join(log_lines)
        self.log_text.setPlainText(new_log)
        
        # Scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def clear_log(self):
        """Clear activity log"""
        self.log_text.setPlainText("Log cleared!")
    
    def clear_history(self):
        """Clear history and statistics"""
        self.status_history.clear()
        self.timestamps.clear()
        self.uptime_data.clear()
        self.total_checks = 0
        self.successful_checks = 0
        
        self.total_checks_label.setText("Total Checks: 0")
        self.uptime_label.setText("Uptime: 0.0%")
        self.add_to_log("History and statistics cleared!")
        
        # Clear graph based on widget type
        if hasattr(self.plot_widget, 'clear_graph'):
            # Enhanced widget
            self.plot_widget.clear_graph()
        elif hasattr(self, 'uptime_line'):
            # Standard widget
            self.uptime_line.setData([], [])
    
    def show_notification(self, title, message):
        """Show notification with optional sound"""
        try:
            # Play sound first if enabled
            if self.play_custom_sound:
                threading.Thread(target=self.play_sound, daemon=True).start()
            
            msg_box = QMessageBox()
            msg_box.setWindowTitle(title)
            msg_box.setText(message)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()
        except Exception as e:
            print(f"Notification error: {e}")
    
    def toggle_change_notifications(self, checked):
        """Toggle change notifications"""
        self.notification_on_change = checked
        self.user_settings.set("notification_on_change", checked)
    
    def toggle_down_notifications(self, checked):
        """Toggle down notifications"""
        self.notification_when_down = checked
        self.user_settings.set("notification_when_down", checked)
    
    def toggle_sound_notifications(self, checked):
        """Toggle sound with notifications"""
        self.play_custom_sound = checked
        self.user_settings.set("play_custom_sound", checked)
    
    def toggle_no_action(self, checked):
        """Toggle no action option"""
        if checked:
            self.auto_action_mode = "none"
            self.focus_existing_cb.setChecked(False)
            self.launch_and_focus_cb.setChecked(False)
            self.user_settings.set("auto_action_mode", "none")
    
    def toggle_focus_existing(self, checked):
        """Toggle focus existing option"""
        if checked:
            self.auto_action_mode = "focus_existing"
            self.no_action_cb.setChecked(False)
            self.launch_and_focus_cb.setChecked(False)
            self.user_settings.set("auto_action_mode", "focus_existing")
    
    def toggle_launch_and_focus(self, checked):
        """Toggle launch and focus option"""
        if checked:
            if not self.client_executable_path:
                # Show message and revert
                self.add_to_log("Please select a client executable first!")
                self.launch_and_focus_cb.setChecked(False)
                return
            
            self.auto_action_mode = "launch_and_focus"
            self.no_action_cb.setChecked(False)
            self.focus_existing_cb.setChecked(False)
            self.user_settings.set("auto_action_mode", "launch_and_focus")

def main():
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("Lazy Project Epoch Server Monitor")
    app.setApplicationVersion("1.0")
    
    monitor = ServerMonitor()
    monitor.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()