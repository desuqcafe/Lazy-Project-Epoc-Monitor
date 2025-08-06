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
import requests
import hashlib

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QPushButton, QSpinBox, QCheckBox, 
                           QTextEdit, QGroupBox, QFileDialog, QMessageBox, QFrame,
                           QGridLayout, QSizePolicy, QComboBox, QSlider)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QPalette, QColor
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton, QCheckBox, QLineEdit, QFileDialog, QMessageBox, QTextEdit, QGroupBox


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

class UserSettings:    
    def __init__(self, filename="monitor_settings.json"):
        self.filename = filename
        self.defaults = {
            "client_executable_path": "",
            "selected_sound": "gotime.mp3",
            "play_custom_sound": False,
            "sound_volume": 35,
            "notification_on_change": True,
            "notification_when_down": False,
            "auto_action_mode": "none",
            "check_interval": 5,
            "window_geometry": None,
            "monitor_auth": True,
            "monitor_kezan": True,
            "monitor_gurubashi": True,
            "monitor_manifest": True,
            "manifest_check_interval": 30,
            "sound_notifications_enabled": True,
            "settings_location": "auto",
            "custom_settings_path": "",
            "auto_save_settings": True,
            "keep_settings_cache": True,
            "last_known_build_version": None,
            "build_version_history": [],
            "notify_on_build_update": True,
            "manifest_client_directory": ""
        }
        self.settings = self.defaults.copy()
        self.current_settings_path = None
        self._initialize_settings_location()

    def update_build_version(self, new_version):
        """Update the build version and track history"""
        old_version = self.settings.get("last_known_build_version")
        
        if old_version and old_version != new_version:
            history = self.settings.get("build_version_history", [])
            from datetime import datetime
            history.append({
                "from_version": old_version,
                "to_version": new_version,
                "timestamp": datetime.now().isoformat()
            })
            
            # Keep only last 10 version changes
            if len(history) > 10:
                history = history[-10:]
            
            self.settings["build_version_history"] = history
            
        self.settings["last_known_build_version"] = new_version
        
        if self.settings.get("auto_save_settings", True):
            self.save()
            
        return old_version

    def get_version_change_info(self):
        """Get information about recent version changes"""
        history = self.settings.get("build_version_history", [])
        current = self.settings.get("last_known_build_version")
        
        return {
            "current_version": current,
            "history": history,
            "has_history": len(history) > 0
        }

    def _initialize_settings_location(self):
        """Initialize settings location based on user preference"""
        temp_path = self._get_auto_settings_path()
        if os.path.exists(temp_path):
            try:
                with open(temp_path, 'r', encoding='utf-8') as f:
                    temp_settings = json.load(f)
                    location_pref = temp_settings.get("settings_location", "auto")
                    custom_path = temp_settings.get("custom_settings_path", "")
            except:
                location_pref = "auto"
                custom_path = ""
        else:
            location_pref = "auto"
            custom_path = ""
        
        self.current_settings_path = self._get_settings_path_by_preference(location_pref, custom_path)
        print(f"Settings will be stored at: {self.current_settings_path}")

    def _get_settings_path_by_preference(self, location_pref, custom_path=""):
        """Get settings path based on user preference"""
        if location_pref == "portable":
            # Next to executable/script
            return self._get_portable_path()
        elif location_pref == "appdata":
            # User's AppData/config directory
            return self._get_appdata_path()
        elif location_pref == "custom" and custom_path and os.path.exists(os.path.dirname(custom_path)):
            # Custom user-specified path
            return custom_path
        else:
            # Auto-detect best location
            return self._get_auto_settings_path()
        
    def _get_portable_path(self):
        """Get portable path (next to executable)"""
        try:
            if getattr(sys, 'frozen', False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = os.path.dirname(os.path.abspath(__file__))
            return os.path.join(app_dir, self.filename)
        except:
            return self._get_appdata_path()
        
    def _get_appdata_path(self):
        """Get AppData/config directory path"""
        try:
            if sys.platform == "win32":
                local_appdata = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
                app_folder = os.path.join(local_appdata, 'ProjectEpochMonitor')
            else:
                app_folder = os.path.expanduser('~/.config/ProjectEpochMonitor')
            
            os.makedirs(app_folder, exist_ok=True)
            return os.path.join(app_folder, self.filename)
        except:
            return os.path.join(os.path.expanduser('~'), f'.{self.filename}')
    
    def _get_auto_settings_path(self):
        """Auto-detect best writable location"""
        # Try portable first, then AppData
        portable_path = self._get_portable_path()
        if self._test_write_access(portable_path):
            return portable_path
        else:
            return self._get_appdata_path()
        
    def _test_write_access(self, path):
        """Test if we can write to a location"""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            test_file = path + '.test'
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return True
        except:
            return False
        
    def change_settings_location(self, new_location, custom_path=""):
        """Change where settings are stored"""
        old_path = self.current_settings_path
        new_path = self._get_settings_path_by_preference(new_location, custom_path)
        
        # Test if new location is writable
        if not self._test_write_access(new_path):
            raise PermissionError(f"Cannot write to location: {new_path}")
        
        # Update settings with new location preference
        self.settings["settings_location"] = new_location
        self.settings["custom_settings_path"] = custom_path
        
        # If there are existing settings, copy them to new location
        if os.path.exists(old_path) and old_path != new_path:
            try:
                # Save to new location
                old_current_path = self.current_settings_path
                self.current_settings_path = new_path
                self.save()
                
                # Ask user if they want to delete old settings
                return old_path  # Return old path so UI can ask user about deletion
            except Exception as e:
                # Revert on error
                self.current_settings_path = old_path
                raise e
        else:
            self.current_settings_path = new_path
            self.save()
            return None
        
    def clear_all_cache(self):
        """Clear all cached settings and data"""
        possible_locations = [
            self._get_portable_path(),
            self._get_appdata_path(),
            os.path.join(os.path.expanduser('~'), f'.{self.filename}')
        ]
        
        cleared_files = []
        for path in possible_locations:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    cleared_files.append(path)
                except Exception as e:
                    print(f"Could not delete {path}: {e}")
        
        # Reset to defaults
        self.settings = self.defaults.copy()
        return cleared_files
    
    def get_all_settings_locations(self):
        """Get info about all possible settings locations"""
        locations = {
            "portable": {
                "path": self._get_portable_path(),
                "exists": os.path.exists(self._get_portable_path()),
                "writable": self._test_write_access(self._get_portable_path()),
                "description": "Next to application (portable)"
            },
            "appdata": {
                "path": self._get_appdata_path(),
                "exists": os.path.exists(self._get_appdata_path()),
                "writable": self._test_write_access(self._get_appdata_path()),
                "description": "User AppData folder (recommended)"
            },
            "current": {
                "path": self.current_settings_path if self.current_settings_path else "Not set",
                "exists": os.path.exists(self.current_settings_path) if self.current_settings_path else False,
                "writable": self._test_write_access(self.current_settings_path) if self.current_settings_path else False,
                "description": "Currently active location"
            }
        }
        return locations

    def _get_settings_path(self, filename):
        try:
            # Try multiple locations in order of preference
            possible_paths = []
            
            # 1. Try the executable/script directory first (if writable)
            try:
                if getattr(sys, 'frozen', False):
                    # Running as executable
                    app_dir = os.path.dirname(sys.executable)
                else:
                    # Running as script
                    app_dir = os.path.dirname(os.path.abspath(__file__))
                
                # Test if we can write to this directory
                test_file = os.path.join(app_dir, '.write_test')
                try:
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.remove(test_file)
                    # If we get here, directory is writable
                    possible_paths.append(os.path.join(app_dir, filename))
                except (PermissionError, OSError):
                    pass  # Directory not writable, try next option
                    
            except Exception:
                pass  # Skip this option if it fails
            
            # 2. Try user's AppData/Local directory (Windows) or home directory (others)
            try:
                if sys.platform == "win32":
                    # Windows: Use %LOCALAPPDATA%
                    local_appdata = os.environ.get('LOCALAPPDATA')
                    if local_appdata:
                        app_folder = os.path.join(local_appdata, 'ProjectEpochMonitor')
                        os.makedirs(app_folder, exist_ok=True)
                        possible_paths.append(os.path.join(app_folder, filename))
                else:
                    # Linux/Mac: Use ~/.config or home directory
                    config_dir = os.path.expanduser('~/.config/ProjectEpochMonitor')
                    os.makedirs(config_dir, exist_ok=True)
                    possible_paths.append(os.path.join(config_dir, filename))
            except Exception:
                pass
            
            # 3. Fallback: User's home directory
            try:
                home_dir = os.path.expanduser('~')
                possible_paths.append(os.path.join(home_dir, f'.{filename}'))
            except Exception:
                pass
            
            # 4. Last resort: temp directory (settings won't persist between reboots)
            import tempfile
            temp_dir = tempfile.gettempdir()
            possible_paths.append(os.path.join(temp_dir, f'ProjectEpochMonitor_{filename}'))
            
            # Test each path and return the first writable one
            for path in possible_paths:
                try:
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    
                    # Test write access
                    test_file = path + '.test'
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.remove(test_file)
                    
                    print(f"Settings will be saved to: {path}")
                    return path
                    
                except (PermissionError, OSError):
                    continue  # Try next path
            
            # If all else fails, return the temp path (last in list)
            print(f"Warning: Using temporary settings location: {possible_paths[-1]}")
            return possible_paths[-1]
            
        except Exception as e:
            # Emergency fallback
            fallback_path = os.path.join(tempfile.gettempdir(), filename)
            print(f"Error determining settings path, using fallback: {fallback_path}")
            return fallback_path
    
    def load(self):
        """Load settings from JSON file"""
        try:
            if self.current_settings_path and os.path.exists(self.current_settings_path):
                with open(self.current_settings_path, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    self.settings = self.defaults.copy()
                    self.settings.update(loaded_settings)
                    print(f"Settings loaded from: {self.current_settings_path}")
            else:
                print(f"No existing settings file found, using defaults")
                self.settings = self.defaults.copy()
        except Exception as e:
            print(f"Error loading settings: {e}, using defaults")
            self.settings = self.defaults.copy()
        
        return self.settings
    
    def save(self, settings_dict=None):
        """Save settings to JSON file"""
        if not self.settings.get("auto_save_settings", True):
            return  # Auto-save disabled
            
        if settings_dict:
            self.settings.update(settings_dict)
        
        try:
            if not self.current_settings_path:
                return
                
            os.makedirs(os.path.dirname(self.current_settings_path), exist_ok=True)
            
            temp_filename = self.current_settings_path + '.tmp'
            with open(temp_filename, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            
            if os.path.exists(self.current_settings_path):
                os.remove(self.current_settings_path)
            os.rename(temp_filename, self.current_settings_path)
            
        except Exception as e:
            print(f"Error saving settings: {e}")
            try:
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
            except:
                pass

    def manual_save(self):
        """Force save settings even if auto-save is disabled"""
        auto_save_temp = self.settings.get("auto_save_settings", True)
        self.settings["auto_save_settings"] = True
        self.save()
        self.settings["auto_save_settings"] = auto_save_temp
    
    def get(self, key, default=None):
        """Get a setting value"""
        return self.settings.get(key, default)
    
    def set(self, key, value):
        """Set a setting value and save immediately"""
        self.settings[key] = value
        if self.settings.get("auto_save_settings", True):
            self.save()
    
    def update_multiple(self, settings_dict):
        """Update multiple settings and save once"""
        self.settings.update(settings_dict)
        if self.settings.get("auto_save_settings", True):
            self.save()

class ServerMonitorThread(QThread):
    status_update = pyqtSignal(str, bool, float)  # server_name, is_up, check_duration
    
    def __init__(self, server_name, server_host, port, parent=None):
        super().__init__(parent)
        self.server_name = server_name
        self.server_host = server_host
        self.port = port
        self.running = False
        self.check_interval = 5
        self._stop_event = threading.Event()

        self.known_ips = set()
        if server_name in ["Kezan", "Gurubashi"]:
            # Add both known server IPs for realm servers
            self.known_ips.add("57.128.162.57")  # DNS resolved IP
            self.known_ips.add("51.77.108.104")  # Actually connected IP

    def __del__(self):
        try:
            self.stop()
            if hasattr(self, '_stop_event'):
                self._stop_event.set()
        except:
            pass  # Ignore errors during cleanup
        
    def run(self):
        while self.running and not self._stop_event.is_set():
            start_time = time.time()
            is_up = self.check_server()
            check_duration = time.time() - start_time
            
            self.status_update.emit(self.server_name, is_up, check_duration)
            
            remaining_sleep = max(0, self.check_interval - check_duration)
            
            if remaining_sleep > 0:
                self._stop_event.wait(remaining_sleep)
    
    def check_server(self):
        # For Auth server, just check the main hostname
        if self.server_name == "Auth":
            return self._check_single_host(self.server_host)
        
        if self.known_ips:
            successful_connections = 0
            rejection_detected = 0
            total_attempts = 0
            
            # Try each known IP
            for ip in self.known_ips:
                total_attempts += 1
                result = self._check_single_host(ip)
                if result:
                    successful_connections += 1
                else:
                    # Check if this was a rejection vs connection failure
                    if self._quick_connection_test(ip):
                        rejection_detected += 1
            
            # Also try the original hostname
            total_attempts += 1
            result = self._check_single_host(self.server_host) 
            if result:
                successful_connections += 1
            else:
                if self._quick_connection_test(self.server_host):
                    rejection_detected += 1
            
            # - If we can connect but get rejections, server is "down" for game purposes
            # - If we get successful game-like responses, server is truly "up"
            if successful_connections > 0:
                return True  # At least one IP is accepting game connections properly
            elif rejection_detected > 0:
                return False  # Server is up at network level but rejecting game connections
            else:
                return False  # Complete connection failure
        else:
            # Fallback to original behavior
            return self._check_single_host(self.server_host)
        
    def detect_connection_rejections(self):
        """
        Advanced method to detect if servers are rejecting actual game connections
        by analyzing connection patterns and timing
        """
        try:
            # Get current netstat data
            result = subprocess.run(['netstat', '-an'], capture_output=True, text=True, shell=True)
            lines = result.stdout.split('\n')
            
            # Look for patterns that suggest connection rejection
            rejection_indicators = {}
            
            for line in lines:
                if 'TIME_WAIT' in line and (':8085' in line or ':8086' in line):
                    # Many TIME_WAIT connections might indicate rapid disconnections
                    # This could suggest the server is accepting but immediately dropping connections
                    parts = line.split()
                    if len(parts) >= 3:
                        remote_addr = parts[2]
                        if ':8085' in remote_addr:
                            rejection_indicators['Kezan'] = rejection_indicators.get('Kezan', 0) + 1
                        elif ':8086' in remote_addr:
                            rejection_indicators['Gurubashi'] = rejection_indicators.get('Gurubashi', 0) + 1
            
            # Analyze rejection patterns
            results = {}
            for server, count in rejection_indicators.items():
                if count > 3:  # More than 3 TIME_WAIT connections suggests issues
                    results[server] = f"Possible connection rejection detected ({count} recent disconnections)"
            
            return results
            
        except Exception as e:
            return {}
        
    def _quick_connection_test(self, host):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, self.port))
            sock.close()
            return result == 0  # True if we can connect (even if rejected later)
        except:
            return False
        
    def _check_single_host(self, host):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            
            start_time = time.time()
            result = sock.connect_ex((host, self.port))
            connect_time = time.time() - start_time
            
            if result == 0:
                # Connection successful, now test if server is actually accepting game connections
                try:
                    if self.server_name in ["Kezan", "Gurubashi"]:
                        # realm server check
                        return self._test_realm_server_acceptance(sock, connect_time)
                    else:
                        # For Auth server, just check basic connectivity
                        return True
                except Exception as e:
                    # If any error occurs, assume server is rejecting connections
                    return False
                finally:
                    # Ensure socket is always closed
                    try:
                        sock.close()
                    except:
                        pass
            else:
                return False
                
        except Exception as e:
            return False
        finally:
            # Guarantee socket cleanup even if exceptions occur
            if sock:
                try:
                    sock.close()
                except:
                    pass
            
    def _test_realm_server_acceptance(self, sock, connect_time):
        try:
            # Set shorter timeout for response testing
            sock.settimeout(2)
            
            # Send a minimal WoW-like probe packet
            # This mimics the initial connection attempt that a WoW client would make
            test_packet = b'\x00\x04\x01\x00'  # Basic realm connection probe
            
            try:
                sock.send(test_packet)
                
                # Try to receive a response
                response = sock.recv(1024)
                
                # If we get ANY response, server is likely accepting connections
                if len(response) > 0:
                    return True
                else:
                    # No response might indicate rejection
                    return connect_time < 1.0  # Still consider "up" if connection was fast
                    
            except socket.timeout:
                # No response within timeout - server might be rejecting connections
                # Classify based on connection speed
                if connect_time < 0.5:
                    # Fast connection but no response - might be maintenance mode
                    return False  # Consider this "down" for game purposes
                elif connect_time < 1.5:
                    # Moderate connection time - might be overloaded
                    return True   # Still consider "up" but problematic
                else:
                    # Slow connection - definitely having issues
                    return False
                    
            except ConnectionResetError:
                # Server actively rejected the connection after accepting it
                return False  # Definitely rejecting game connections
                
            except Exception as e:
                # Any other error suggests server is not properly accepting connections
                return False
                
        except Exception as e:
            return False
    
    def add_known_ip(self, ip):
        """Add a new IP address to check for this server"""
        if self.server_name in ["Kezan", "Gurubashi"]:
            self.known_ips.add(ip)
    
    def set_interval(self, interval):
        self.check_interval = interval
    
    def stop(self):
        self.running = False
        if hasattr(self, '_stop_event'):
            self._stop_event.set()

class ServerCard(QWidget):
    """Individual server status card widget"""
    
    # Signal emitted when monitoring checkbox state changes
    monitoring_toggled = pyqtSignal(str, bool)  # server_name, enabled
    
    def __init__(self, server_name, server_type, port, parent=None):
        super().__init__(parent)
        self.server_name = server_name
        self.server_type = server_type
        self.port = port
        self.is_up = False
        self.total_checks = 0
        self.successful_checks = 0
        self.last_check_time = None
        self.is_monitoring_disabled = False
        self.is_starting = False
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the server card UI"""
        self.setStyleSheet("""
            QWidget {
                background-color: #404040;
                border: 2px solid #555555;
                border-radius: 8px;
                margin: 2px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        
        # Header with server name and type
        header_layout = QHBoxLayout()
        
        self.name_label = QLabel(self.server_name)
        self.name_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffffff;")
        header_layout.addWidget(self.name_label)
        
        self.type_label = QLabel(f"({self.server_type})")
        self.type_label.setStyleSheet("font-size: 11px; color: #cccccc;")
        header_layout.addWidget(self.type_label)
        
        header_layout.addStretch()
        
        # Status indicator
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #757575; font-size: 20px;")
        header_layout.addWidget(self.status_indicator)
        
        layout.addLayout(header_layout)
        
        # Port and status text
        info_layout = QHBoxLayout()
        
        self.port_label = QLabel(f"Port: {self.port}")
        self.port_label.setStyleSheet("font-size: 10px; color: #999999;")
        info_layout.addWidget(self.port_label)
        
        info_layout.addStretch()
        
        self.status_text = QLabel("STOPPED")
        self.status_text.setStyleSheet("font-weight: bold; font-size: 12px; color: #ffab40;")
        info_layout.addWidget(self.status_text)
        
        layout.addLayout(info_layout)
        
        # Stats row
        stats_layout = QHBoxLayout()
        
        self.uptime_label = QLabel("Uptime: 0%")
        self.uptime_label.setStyleSheet("font-size: 10px; color: #cccccc;")
        stats_layout.addWidget(self.uptime_label)
        
        stats_layout.addStretch()
        
        self.last_check_label = QLabel("Never")
        self.last_check_label.setStyleSheet("font-size: 10px; color: #999999;")
        stats_layout.addWidget(self.last_check_label)
        
        layout.addLayout(stats_layout)
        
        # Enable checkbox - connect to signal emission
        self.enabled_cb = QCheckBox("Monitor this server")
        self.enabled_cb.setChecked(True)
        self.enabled_cb.setStyleSheet("font-size: 10px; color: #cccccc;")
        self.enabled_cb.toggled.connect(self._on_monitoring_toggled)
        layout.addWidget(self.enabled_cb)
    
    def _on_monitoring_toggled(self, checked):
        """Handle monitoring checkbox toggle and emit signal"""
        self.monitoring_toggled.emit(self.server_name, checked)
    
    def update_status(self, is_up, check_duration):
        if self.is_monitoring_disabled:
            return  # Don't update disabled cards!
        
        # Clear starting state when we get first real update
        if self.is_starting:
            self.is_starting = False
        
        self.is_up = is_up
        self.total_checks += 1
        if is_up:
            self.successful_checks += 1
        
        self.last_check_time = datetime.now()
        
        # Update status display
        status_text = "ONLINE" if is_up else "OFFLINE"
        color = "#66bb6a" if is_up else "#f44336"
        timeout_color = "#ff9800"  # Orange for timeout
        
        # Check if it's likely a timeout (longer check duration)
        if not is_up and check_duration > 1.8:  # Close to our 2s timeout
            status_text = "TIMEOUT"
            color = timeout_color
        
        self.status_text.setText(status_text)
        self.status_text.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {color};")
        self.status_indicator.setStyleSheet(f"color: {color}; font-size: 20px;")
        
        border_color = color
        self.setStyleSheet(f"""
            QWidget {{
                background-color: #404040;
                border: 2px solid {border_color};
                border-radius: 8px;
                margin: 2px;
            }}
        """)
        
        # Update uptime
        if self.total_checks > 0:
            uptime_percent = (self.successful_checks / self.total_checks) * 100
            self.uptime_label.setText(f"Uptime: {uptime_percent:.1f}%")
        
        # Update last check time
        time_str = self.last_check_time.strftime("%H:%M:%S")
        self.last_check_label.setText(f"Last: {time_str}")

    def set_to_starting_state(self):
        self.is_monitoring_disabled = False
        self.is_starting = True
        
        self.status_text.setText("STARTING...")
        self.status_text.setStyleSheet("font-weight: bold; font-size: 12px; color: #64b5f6;")  # Blue color
        self.status_indicator.setStyleSheet("color: #64b5f6; font-size: 20px;")
        
        self.setStyleSheet("""
            QWidget {
                background-color: #404040;
                border: 2px solid #64b5f6;
                border-radius: 8px;
                margin: 2px;
            }
        """)
        
        # Update last check to show it's initializing
        self.last_check_label.setText("Initializing...")
    
    def reset_stats(self):
        """Reset statistics for this server"""
        self.total_checks = 0
        self.successful_checks = 0
        self.uptime_label.setText("Uptime: 0%")
        self.last_check_label.setText("Never")
        
        # Reset to default appearance
        self.status_text.setText("STOPPED")
        self.status_text.setStyleSheet("font-weight: bold; font-size: 12px; color: #ffab40;")
        self.status_indicator.setStyleSheet("color: #757575; font-size: 20px;")
        self.setStyleSheet("""
            QWidget {
                background-color: #404040;
                border: 2px solid #555555;
                border-radius: 8px;
                margin: 2px;
            }
        """)
        
        # Clear all states when resetting
        self.is_monitoring_disabled = False
        self.is_starting = False
    
    def set_to_disabled_state(self):
        """Set card to disabled monitoring state while keeping stats"""
        self.is_monitoring_disabled = True
        self.is_starting = False  # Clear starting state
        
        self.status_text.setText("DISABLED")
        self.status_text.setStyleSheet("font-weight: bold; font-size: 12px; color: #666666;")
        self.status_indicator.setStyleSheet("color: #666666; font-size: 20px;")
        self.setStyleSheet("""
            QWidget {
                background-color: #353535;
                border: 2px solid #444444;
                border-radius: 8px;
                margin: 2px;
            }
        """)

    def set_to_enabled_state(self):
        self.is_monitoring_disabled = False
        self.is_starting = False  # Clear starting state
        
        # Reset to default "STOPPED" appearance until monitoring starts
        self.status_text.setText("STOPPED")
        self.status_text.setStyleSheet("font-weight: bold; font-size: 12px; color: #ffab40;")
        self.status_indicator.setStyleSheet("color: #757575; font-size: 20px;")
        self.setStyleSheet("""
            QWidget {
                background-color: #404040;
                border: 2px solid #555555;
                border-radius: 8px;
                margin: 2px;
            }
        """)

class ServerMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Server configurations
        self.servers = {
            "Auth": {"host": "game.project-epoch.net", "port": 3724, "type": "Login"},
            "Kezan": {"host": "game.project-epoch.net", "port": 8085, "type": "PvE Realm"},
            "Gurubashi": {"host": "game.project-epoch.net", "port": 8086, "type": "PvP Realm"},
            "Game Client": {"host": "updater.project-epoch.net", "port": 443, "type": "Manifest"}  # NEW
        }
        
        self.user_settings = UserSettings()
        settings = self.user_settings.load()
        
        self.sound_notifications_enabled = settings.get("sound_notifications_enabled", True)
        self.auto_action_mode = settings["auto_action_mode"]
        self.client_executable_path = settings["client_executable_path"]
        self.selected_sound = settings["selected_sound"]
        self.sound_volume = settings["sound_volume"]
        self.is_simulating = False
        
        self.manifest_check_interval = settings.get("manifest_check_interval", 30)
        self.notify_on_build_update = settings.get("notify_on_build_update", True)
        
        self.audio_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "audio")
        self.available_sounds = self.scan_audio_files()
        
        if self.selected_sound not in self.available_sounds:
            self.selected_sound = "gotime.mp3" if "gotime.mp3" in self.available_sounds else "System Default"
        
        self.monitor_threads = {}
        self.server_cards = {}
        self.manifest_thread = None
        self.start_time = None
        self.max_log_lines = 25
        
        self.threads_to_cleanup = []
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._cleanup_finished_threads)
        self.cleanup_timer.start(1000)
        
        self.init_ui()
        self.load_ui_settings()
        self.update_client_button_states()

    def _cleanup_finished_threads(self):
        if not self.threads_to_cleanup:
            return
        
        cleaned_up = []
        for thread in self.threads_to_cleanup[:]:
            try:
                if thread.isFinished():
                    cleaned_up.append(thread)
                    thread.deleteLater()
                elif not thread.running:
                    if not hasattr(thread, '_stop_time'):
                        thread._stop_time = time.time()
                    elif time.time() - thread._stop_time > 5:
                        thread.terminate()
                        cleaned_up.append(thread)
                elif hasattr(self, '_shutting_down') and self._shutting_down:
                    if not hasattr(thread, '_stop_time'):
                        thread._stop_time = time.time()
                    elif time.time() - thread._stop_time > 2:
                        thread.terminate()
                        cleaned_up.append(thread)
            except Exception:
                cleaned_up.append(thread)
        
        for thread in cleaned_up:
            if thread in self.threads_to_cleanup:
                self.threads_to_cleanup.remove(thread)


    def load_ui_settings(self):
        """Load UI settings from user settings including client directory restoration"""
        settings = self.user_settings.settings
        
        # Load check interval
        interval = max(2, min(300, settings.get("check_interval", 5)))
        self.delay_spinbox.setValue(interval)
        
        # Load sound settings
        self.sound_notifications_cb.setChecked(self.sound_notifications_enabled)
        
        volume = max(0, min(100, settings.get("sound_volume", 35)))
        self.sound_volume = volume
        self.volume_slider.setValue(volume)
        self.volume_label.setText(f"{volume}%")
        
        if self.selected_sound in self.available_sounds:
            self.sound_combo.setCurrentText(self.selected_sound)
        
        # Update auto-action checkboxes
        self.update_auto_action_checkboxes()
        
        # Load executable path and update UI
        if self.client_executable_path and os.path.exists(self.client_executable_path):
            filename = os.path.basename(self.client_executable_path)
            self.client_path_label.setText(f"Client: {filename}")
            self.client_path_label.setStyleSheet("color: #66bb6a; font-weight: bold; font-size: 11px;")
        
        # Load server monitoring checkboxes
        self.server_cards["Auth"].enabled_cb.setChecked(settings.get("monitor_auth", True))
        self.server_cards["Kezan"].enabled_cb.setChecked(settings.get("monitor_kezan", True))
        self.server_cards["Gurubashi"].enabled_cb.setChecked(settings.get("monitor_gurubashi", True))
        self.server_cards["Game Client"].enabled_cb.setChecked(settings.get("monitor_manifest", True))
        
        # Load manifest settings
        self.manifest_check_interval = settings.get("manifest_check_interval", 30)
        self.notify_on_build_update = settings.get("notify_on_build_update", True)
        
        # Load current version for manifest card
        current_version = settings.get("last_known_build_version")
        if current_version:
            manifest_card = self.server_cards["Game Client"]
            manifest_card.current_version = current_version
            manifest_card.version_label.setText(f"Version: {current_version}")
        
        # Load manually saved client directory first
        saved_client_dir = settings.get("manifest_client_directory", "")
        client_dir_restored = False
        
        if saved_client_dir and os.path.exists(saved_client_dir):
            if "Game Client" in self.server_cards:
                manifest_card = self.server_cards["Game Client"]
                # Mark restored directory as manual since user saved it
                if manifest_card.set_client_directory_path(saved_client_dir, is_manual=True):
                    dir_name = os.path.basename(saved_client_dir)
                    # self.add_to_log(f"📁 Restored saved client directory: {dir_name}")
                    client_dir_restored = True
                else:
                    # Directory exists but is invalid - clear the setting
                    self.user_settings.set("manifest_client_directory", "")
                    self.add_to_log("⚠️ Saved client directory is invalid, cleared from settings")
        elif saved_client_dir:
            # Directory was saved but no longer exists
            self.user_settings.set("manifest_client_directory", "")
            self.add_to_log("⚠️ Saved client directory no longer exists, cleared from settings")
        
        # FALLBACK: Auto-detection from executable path (only if no manual directory was restored)
        if not client_dir_restored and self.client_executable_path and os.path.exists(self.client_executable_path):
            if "Game Client" in self.server_cards:
                manifest_card = self.server_cards["Game Client"]
                
                # Only try auto-detection if no client directory is currently set
                if not manifest_card.client_directory:
                    # This will be marked as auto-detected (is_manual=False)
                    auto_detected = manifest_card.set_client_directory(self.client_executable_path)
                    if auto_detected:
                        self.add_to_log(f"🔍 Auto-detected client directory from executable path")
                    else:
                        self.add_to_log(f"💡 Could not auto-detect client directory - use '📁 Set Client Dir' button if needed")
                else:
                    # This shouldn't happen since we handle manual directory above, but just in case
                    manual_dir = os.path.basename(manifest_card.client_directory)
                    self.add_to_log(f"📂 Client directory already set: {manual_dir}")
        
        # Restore window geometry
        self._restore_window_geometry(settings.get("window_geometry"))

    def _restore_window_geometry(self, geometry):
        if not geometry or len(geometry) != 4:
            return  # Invalid geometry data
        
        try:
            x, y, width, height = geometry
            
            # Get available screen geometry
            available_geometry = QApplication.primaryScreen().availableGeometry()
            
            # Validate the restored position is at least partially on screen
            if (x + width < available_geometry.left() or 
                x > available_geometry.right() or
                y + height < available_geometry.top() or 
                y > available_geometry.bottom()):
                # Window would be completely off-screen, don't restore
                self.add_to_log("Saved window position is off-screen, using default")
                return
            
            width = max(width, 600)
            height = max(height, 400)
            
            x = max(available_geometry.left(), 
                    min(x, available_geometry.right() - width))
            y = max(available_geometry.top(), 
                    min(y, available_geometry.bottom() - height))
            
            self.setGeometry(x, y, width, height)
            
        except (ValueError, TypeError, AttributeError) as e:
            self.add_to_log(f"Error restoring window geometry: {e}")

    def clear_log_only(self):
        """Clear activity log without affecting stats or settings"""
        self.log_text.setPlainText("Activity log cleared...")
        
    def save_current_settings(self):
        current_settings = {
            "client_executable_path": self.client_executable_path,
            "selected_sound": self.selected_sound,
            "sound_notifications_enabled": self.sound_notifications_enabled,
            "sound_volume": self.sound_volume,
            "auto_action_mode": self.auto_action_mode,
            "check_interval": self.delay_spinbox.value(),
            "window_geometry": [self.x(), self.y(), self.width(), self.height()],
            "monitor_auth": self.server_cards["Auth"].enabled_cb.isChecked(),
            "monitor_kezan": self.server_cards["Kezan"].enabled_cb.isChecked(),
            "monitor_gurubashi": self.server_cards["Gurubashi"].enabled_cb.isChecked(),
            "monitor_manifest": self.server_cards["Game Client"].enabled_cb.isChecked(),
            "manifest_check_interval": self.manifest_check_interval,
            "notify_on_build_update": self.notify_on_build_update,
            "manifest_client_directory": getattr(self.server_cards["Game Client"], 'client_directory', "") or ""
        }
        self.user_settings.update_multiple(current_settings)
    
    def closeEvent(self, event):
        """Non-blocking close event handler"""
        self.save_current_settings()
        self._shutting_down = True
        
        self.stop_all_monitoring()
        
        QApplication.processEvents()
        
        event.accept()

    def scan_audio_files(self):
        sounds = ["System Default"]
        
        possible_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "audio"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                self.audio_path = path
                try:
                    for file in os.listdir(path):
                        if file.lower().endswith(('.mp3', '.wav', '.ogg')):
                            sounds.append(file)
                    sounds.sort()
                    break
                except Exception as e:
                    print(f"Error scanning audio folder: {e}")
        
        return sounds
    
    def get_sound_path(self, sound_name):
        if sound_name == "System Default":
            return None
        return os.path.join(self.audio_path, sound_name)
        
    def init_ui(self):
        self.setWindowTitle("Project Epoch Multi-Server Monitor")
        self.setGeometry(100, 100, 800, 900)
        
        # Set dark theme
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
                width: 16px;
                border-left: 1px solid #555555;
                border-bottom: 1px solid #555555;
                border-top-right-radius: 3px;
                background-color: #555555;
                color: #ffffff;
            }
            QSpinBox::up-button:hover {
                background-color: #666666;
            }
            QSpinBox::up-button:pressed {
                background-color: #333333;
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 16px;
                border-left: 1px solid #555555;
                border-top: 1px solid #555555;
                border-bottom-right-radius: 3px;
                background-color: #555555;
                color: #ffffff;
            }
            QSpinBox::down-button:hover {
                background-color: #666666;
            }
            QSpinBox::down-button:pressed {
                background-color: #333333;
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
            QSlider::groove:horizontal {
                border: 1px solid #555555;
                height: 6px;
                background-color: #404040;
                margin: 2px 0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background-color: #0078d4;
                border: 1px solid #0078d4;
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background-color: #0078d4;
                border-radius: 3px;
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
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)
        
        settings_group = QGroupBox("Settings")
        settings_layout = QGridLayout(settings_group)
        settings_layout.setContentsMargins(8, 12, 8, 8)
        
        settings_layout.addWidget(QLabel("Check every:"), 0, 0)
        self.delay_spinbox = QSpinBox()
        self.delay_spinbox.setRange(2, 300)
        self.delay_spinbox.setValue(5)
        self.delay_spinbox.setSuffix(" seconds")
        self.delay_spinbox.valueChanged.connect(self.on_delay_changed)
        settings_layout.addWidget(self.delay_spinbox, 0, 1)
        
        layout.addWidget(settings_group)
        
        servers_group = QGroupBox("Project Epoch Servers")
        servers_layout = QVBoxLayout(servers_group)
        servers_layout.setContentsMargins(8, 12, 8, 8)
        
        cards_layout = QGridLayout()
        cards_layout.setSpacing(8)
        
        row = 0
        col = 0
        for server_name, config in self.servers.items():
            if server_name == "Game Client":
                card = ManifestServerCard()
            else:
                card = ServerCard(server_name, config["type"], config["port"])
            
            card.monitoring_toggled.connect(self.on_server_monitoring_toggled)
            self.server_cards[server_name] = card
            cards_layout.addWidget(card, row, col)
            
            col += 1
            if col > 1:
                col = 0
                row += 1
        
        servers_layout.addLayout(cards_layout)
        layout.addWidget(servers_group)
        
        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setContentsMargins(8, 12, 8, 8)
        
        monitor_row = QHBoxLayout()
        monitor_row.addWidget(QLabel("Monitor:"))
        
        # Basic monitoring buttons
        self.start_btn = QPushButton("Start All")
        self.start_btn.clicked.connect(self.start_all_monitoring)
        self.stop_btn = QPushButton("Stop All")
        self.stop_btn.clicked.connect(self.stop_all_monitoring)
        self.stop_btn.setEnabled(False)
        monitor_row.addWidget(self.start_btn)
        monitor_row.addWidget(self.stop_btn)
        
        # Stats and utility buttons
        clear_stats_btn = QPushButton("Clear All Stats")
        clear_stats_btn.clicked.connect(self.clear_all_stats)
        monitor_row.addWidget(clear_stats_btn)

        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.clicked.connect(self.clear_log_only)
        clear_log_btn.setToolTip("Clear activity log only")
        clear_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 8px;
                color: #ffffff;
                font-weight: bold;
                min-height: 20px;
                max-width: 80px;
            }
            QPushButton:hover {
                background-color: #505050;
                border-color: #666666;
            }
        """)
        monitor_row.addWidget(clear_log_btn)
        
        detect_btn = QPushButton("Detect Active IPs")
        detect_btn.clicked.connect(self.test_connection_detection)
        detect_btn.setToolTip("Scan for active server connections and update monitoring IPs")
        monitor_row.addWidget(detect_btn)

        # Advanced settings button
        advanced_settings_btn = QPushButton("⚙️ Advanced Settings")
        advanced_settings_btn.clicked.connect(self.open_advanced_settings)
        advanced_settings_btn.setToolTip("Manage settings storage location and cache")
        monitor_row.addWidget(advanced_settings_btn)

        monitor_row.addStretch()
        controls_layout.addLayout(monitor_row)
        
        # Client control row
        client_row = QHBoxLayout()
        client_row.addWidget(QLabel("Client:"))
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self.browse_executable)
        self.test_launch_btn = QPushButton("Test Launch")
        self.test_launch_btn.clicked.connect(self.test_launch_client)
        client_row.addWidget(self.browse_btn)
        client_row.addWidget(self.test_launch_btn)
        client_row.addStretch()
        controls_layout.addLayout(client_row)
        
        self.client_path_label = QLabel("Click 'Browse' to select Project Epoch Launcher")
        self.client_path_label.setStyleSheet("color: #999999; font-style: italic; font-size: 11px;")
        controls_layout.addWidget(self.client_path_label)
        
        layout.addWidget(controls_group)
        
        notif_group = QGroupBox("Sound Notifications")
        notif_layout = QVBoxLayout(notif_group)
        notif_layout.setContentsMargins(8, 12, 8, 8)

        info_text = QLabel("Sound alerts when Kezan/Gurubashi status changes")
        info_text.setStyleSheet("color: #cccccc; font-size: 10px; font-style: italic;")
        notif_layout.addWidget(info_text)

        self.sound_notifications_cb = QCheckBox("Enable sound notifications on realm status change")
        self.sound_notifications_cb.setChecked(True)
        self.sound_notifications_cb.toggled.connect(self.toggle_sound_notifications)
        notif_layout.addWidget(self.sound_notifications_cb)

        sound_row = QHBoxLayout()
        sound_row.addWidget(QLabel("Sound:"))

        self.sound_combo = QComboBox()
        self.sound_combo.addItems(self.available_sounds)
        self.sound_combo.currentTextChanged.connect(self.on_sound_changed)
        sound_row.addWidget(self.sound_combo)

        self.test_sound_btn = QPushButton("Test")
        self.test_sound_btn.setMaximumWidth(60)
        self.test_sound_btn.clicked.connect(self.test_play_sound)
        sound_row.addWidget(self.test_sound_btn)

        sound_row.addWidget(QLabel("Vol:"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(35)
        self.volume_slider.setMaximumWidth(100)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        sound_row.addWidget(self.volume_slider)

        self.volume_label = QLabel("35%")
        self.volume_label.setMinimumWidth(35)
        self.volume_label.setStyleSheet("color: #64b5f6; font-weight: bold;")
        sound_row.addWidget(self.volume_label)

        sound_row.addStretch()

        notif_layout.addLayout(sound_row)
        layout.addWidget(notif_group)
        
        auto_group = QGroupBox("Auto Actions (when any realm comes UP)")
        auto_layout = QVBoxLayout(auto_group)
        auto_layout.setContentsMargins(8, 12, 8, 8)
        
        self.no_action_cb = QCheckBox("Do nothing")
        self.no_action_cb.setChecked(True)
        self.no_action_cb.toggled.connect(self.toggle_no_action)
        
        self.focus_existing_cb = QCheckBox("Find and focus Project Epoch window")
        self.focus_existing_cb.toggled.connect(self.toggle_focus_existing)
        
        self.launch_and_focus_cb = QCheckBox("Launch selected client then focus it")
        self.launch_and_focus_cb.toggled.connect(self.toggle_launch_and_focus)
        
        auto_layout.addWidget(self.no_action_cb)
        auto_layout.addWidget(self.focus_existing_cb)
        auto_layout.addWidget(self.launch_and_focus_cb)
        
        help_row = QHBoxLayout()
        help_text = QLabel("Note: 'Find and focus' searches for Project Epoch windows")
        help_text.setStyleSheet("color: #888888; font-style: italic; font-size: 10px;")
        help_row.addWidget(help_text)
        
        test_focus_btn = QPushButton("Test Focus")
        test_focus_btn.clicked.connect(self.test_focus_client)
        test_focus_btn.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        help_row.addWidget(test_focus_btn)
        help_row.addStretch()
        
        auto_layout.addLayout(help_row)
        layout.addWidget(auto_group)
        
        # Activity log
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 8, 6, 6)
        log_layout.setSpacing(2)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(120)
        self.log_text.setMinimumHeight(120)
        self.log_text.setPlainText("Multi-server monitor ready...")
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)
        layout.addStretch()
        
        # Timer for UI updates
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_runtime_display)
        self.verbose_logging = False
        self.last_status_log = {}


    def open_advanced_settings(self):
        """Open the advanced settings dialog"""
        dialog = AdvancedSettingsDialog(self.user_settings, self)
        dialog.exec()
    
    def on_volume_changed(self, value):
        self.sound_volume = value
        self.volume_label.setText(f"{value}%")
        self.user_settings.set("sound_volume", value)
        
        if value == 0:
            color = "#757575"
        elif value <= 30:
            color = "#ff9800"
        elif value <= 70:
            color = "#64b5f6"
        else:
            color = "#66bb6a"
        
        self.volume_label.setStyleSheet(f"color: {color}; font-weight: bold;")
    
    def on_sound_changed(self, sound_name):
        self.selected_sound = sound_name
        self.user_settings.set("selected_sound", sound_name)
    
    def on_delay_changed(self, value):
        for thread in self.monitor_threads.values():
            if thread.running:
                thread.set_interval(value)
        self.user_settings.set("check_interval", value)
        
    def on_server_monitoring_toggled(self, server_name, enabled):
        if not self.monitor_threads:
            return  # No monitoring is running, nothing to do
        
        if enabled:
            # Show starting state immediately for user feedback
            self.server_cards[server_name].set_to_starting_state()  # NEW!
            
            if server_name not in self.monitor_threads or not self.monitor_threads[server_name].running:
                if self.start_single_server_monitoring(server_name):
                    self.add_to_log(f"Starting monitoring for {server_name}...")
                else:
                    self.add_to_log(f"Failed to start monitoring for {server_name}")
                    # If failed, revert to enabled state
                    self.server_cards[server_name].set_to_enabled_state()
            else:
                self.add_to_log(f"{server_name} is already being monitored")
                # If already monitored, just clear the starting state
                self.server_cards[server_name].set_to_enabled_state()
        else:
            # Disable the card FIRST, then stop monitoring
            self.server_cards[server_name].set_to_disabled_state()
            
            if server_name in self.monitor_threads and self.monitor_threads[server_name].running:
                self.stop_single_server_monitoring(server_name)
                self.add_to_log(f"Stopping monitoring for {server_name}...")

    def start_single_server_monitoring(self, server_name):
        if server_name not in self.servers:
            self.add_to_log(f"Unknown server: {server_name}")
            return False
        
        try:
            if server_name in self.monitor_threads:
                old_thread = self.monitor_threads[server_name]
                if old_thread.running:
                    old_thread.stop()
                    self.threads_to_cleanup.append(old_thread)
                    # Brief pause to let thread begin stopping
                    QApplication.processEvents()
            
            config = self.servers[server_name]
            thread = ServerMonitorThread(
                server_name, 
                config["host"], 
                config["port"]
            )
            thread.set_interval(self.delay_spinbox.value())
            thread.status_update.connect(self.on_status_update)
            thread.running = True
            thread.start()
            
            self.monitor_threads[server_name] = thread
            return True
            
        except Exception as e:
            self.add_to_log(f"Error starting monitoring for {server_name}: {e}")
            return False
        
    def stop_single_server_monitoring(self, server_name):
        """Updated to be consistently non-blocking"""
        if server_name not in self.monitor_threads:
            return False
        
        try:
            thread = self.monitor_threads[server_name]
            if thread.running:
                thread.stop()
                self.threads_to_cleanup.append(thread)
            
            # Remove from active threads immediately
            if server_name in self.monitor_threads:
                del self.monitor_threads[server_name]
            return True
            
        except Exception as e:
            self.add_to_log(f"Error stopping monitoring for {server_name}: {e}")
            return False

    def start_all_monitoring(self):
        if self.start_time is None:
            self.start_time = datetime.now()
        
        self.detect_active_server_connections()
        
        enabled_servers = []
        
        for server_name, card in self.server_cards.items():
            if server_name == "Game Client":
                continue
                
            if card.enabled_cb.isChecked():
                card.set_to_starting_state()
                enabled_servers.append(server_name)
                self.start_single_server_monitoring(server_name)
        
        if self.server_cards["Game Client"].enabled_cb.isChecked():
            self.server_cards["Game Client"].set_to_starting_state()
            if self.start_manifest_monitoring():
                enabled_servers.append("Game Client")
        
        if enabled_servers:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.ui_timer.start(1000)
            
            servers_list = ", ".join(enabled_servers)
            self.add_to_log(f"Started monitoring: {servers_list}")
            
            # Clear previous status tracking to start fresh
            self.last_status_log.clear()
        else:
            self.add_to_log("No servers enabled for monitoring!")

    def test_connection_detection(self):
        detected = self.detect_active_server_connections()
        if detected:
            detected_list = [f"{server}({ip})" for server, ip in detected.items()]
            self.add_to_log(f"Active connections: {', '.join(detected_list)}")
        else:
            self.add_to_log("No active realm connections detected")
        return detected
    
    def _is_valid_ip(self, ip):
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not 0 <= int(part) <= 255:
                    return False
            return True
        except (ValueError, AttributeError):
            return False
        
    def detect_active_server_connections(self):
        try:
            import subprocess
            
            # Check if netstat is available
            try:
                # Run netstat to get active connections
                result = subprocess.run(['netstat', '-an'], 
                                    capture_output=True, 
                                    text=True, 
                                    shell=True,
                                    timeout=10)  # Add timeout
            except subprocess.TimeoutExpired:
                self.add_to_log("⚠️ Network detection timed out")
                return {}
            except FileNotFoundError:
                self.add_to_log("⚠️ netstat command not found")
                return {}
            
            if result.returncode != 0:
                self.add_to_log("⚠️ Failed to run network detection")
                return {}
            
            lines = result.stdout.split('\n')
            detected_ips = {}
            
            for line in lines:
                try:
                    if 'ESTABLISHED' in line and (':8085' in line or ':8086' in line):
                        parts = line.split()
                        if len(parts) >= 3:
                            remote_addr = parts[2]  # Format: IP:PORT
                            
                            if ':8085' in remote_addr:
                                ip = remote_addr.split(':')[0]
                                # Validate IP format
                                if self._is_valid_ip(ip):
                                    detected_ips['Kezan'] = ip
                                    
                            elif ':8086' in remote_addr:
                                ip = remote_addr.split(':')[0]  
                                # Validate IP format
                                if self._is_valid_ip(ip):
                                    detected_ips['Gurubashi'] = ip
                except (IndexError, ValueError):
                    continue  # Skip malformed lines
            
            updated_servers = []
            for server_name, ip in detected_ips.items():
                if server_name in self.monitor_threads:
                    old_ips = self.monitor_threads[server_name].known_ips.copy()
                    self.monitor_threads[server_name].add_known_ip(ip)
                    if ip not in old_ips:
                        updated_servers.append(f"{server_name}({ip})")
            
            if updated_servers:
                self.add_to_log(f"Detected active connections: {', '.join(updated_servers)}")
                
            return detected_ips
            
        except Exception as e:
            self.add_to_log(f"Error detecting connections: {e}")
            return {}

    def stop_all_monitoring(self):
        stopped_servers = []
        
        for server_name, thread in list(self.monitor_threads.items()):
            if thread.running:
                thread.stop()
                thread.wait()
                stopped_servers.append(server_name)
        
        self.monitor_threads.clear()
        
        # Reset all server cards to stopped state and clear all flags
        for card in self.server_cards.values():
            card.is_monitoring_disabled = False
            card.is_starting = False
            card.status_text.setText("STOPPED")
            card.status_text.setStyleSheet("font-weight: bold; font-size: 12px; color: #ffab40;")
            card.status_indicator.setStyleSheet("color: #757575; font-size: 20px;")
            card.setStyleSheet("""
                QWidget {
                    background-color: #404040;
                    border: 2px solid #555555;
                    border-radius: 8px;
                    margin: 2px;
                }
            """)
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.ui_timer.stop()
        
        if stopped_servers:
            servers_list = ", ".join(stopped_servers)
            self.add_to_log(f"Stopped monitoring: {servers_list}")
        else:
            self.add_to_log("Stopped all monitoring - servers reset to STOPPED")
    
    def clear_all_stats(self):
        """Clear statistics but preserve important settings like client directory"""
        for card in self.server_cards.values():
            card.reset_stats()
        
        # Clear status tracking when stats are cleared
        self.last_status_log.clear()
        
        self.add_to_log("Statistics cleared")
    

    def should_send_notification(self, server_name, is_up, status_changed):
        # Only notify for realm servers
        if server_name not in ["Kezan", "Gurubashi"]:
            return False
        
        # Only notify on status changes
        if not status_changed:
            return False
            
        if not self.sound_notifications_enabled:
            return False
            
        # Only notify if server monitoring is enabled for this server
        if not self.server_cards[server_name].enabled_cb.isChecked():
            return False
        
        # Only notify if Auth is online
        if not self.is_auth_server_online():
            return False
                
        return True
    
    def play_system_sound_only(self):
        """Play system notification sound only (for server down/update events)"""
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            elif sys.platform == "darwin":
                os.system("afplay /System/Library/Sounds/Glass.aiff")
            else:
                os.system("paplay /usr/share/sounds/alsa/Front_Left.wav 2>/dev/null || echo -e '\a'")
        except Exception as e:
            print(f"System sound error: {e}")
    
    def detect_actual_playability(self):
        """
        method to detect if servers are actually playable
        by checking for active player connections
        """
        try:
            result = subprocess.run(['netstat', '-an'], capture_output=True, text=True, shell=True)
            lines = result.stdout.split('\n')
            
            # Count active connections to each realm server
            kezan_connections = 0
            gurubashi_connections = 0
            
            for line in lines:
                if 'ESTABLISHED' in line:
                    if ':8085' in line:
                        kezan_connections += 1
                    elif ':8086' in line:
                        gurubashi_connections += 1
            
            # If we have our own connection, subtract 1
            if kezan_connections > 0:
                kezan_connections -= 1
            if gurubashi_connections > 0:
                gurubashi_connections -= 1
            
            playability_status = {}
            if kezan_connections > 0:
                playability_status['Kezan'] = f"Likely playable ({kezan_connections} other connections detected)"
            if gurubashi_connections > 0:
                playability_status['Gurubashi'] = f"Likely playable ({gurubashi_connections} other connections detected)"
            
            return playability_status
            
        except Exception as e:
            return {}
    

    def is_auth_server_online(self):
        if "Auth" in self.server_cards:
            return self.server_cards["Auth"].is_up
        return False
        
    def on_status_update(self, server_name, is_up, check_duration):
        if server_name not in self.monitor_threads:
            return
            
        thread = self.monitor_threads[server_name]
        if not thread.running:
            return
        
        if server_name in self.server_cards:
            old_status = self.server_cards[server_name].is_up
            self.server_cards[server_name].update_status(is_up, check_duration)
            
            status_changed = old_status != is_up
            
            should_log = False
            log_entry = ""
            
            current_time = datetime.now().strftime("%H:%M:%S")
            status_text = "ONLINE" if is_up else ("TIMEOUT" if check_duration > 1.8 else "OFFLINE")
            
            # Determine if this status is worth logging
            last_logged_status = self.last_status_log.get(server_name)
            
            if status_changed:
                # Always log status changes
                should_log = True
                quality_indicator = ""
                
                if is_up:
                    if check_duration < 0.5:
                        quality_indicator = " 🟢"  # Fast connection
                    elif check_duration < 1.0:
                        quality_indicator = " 🟡"  # Moderate connection  
                    elif check_duration < 2.0:
                        quality_indicator = " 🟠"  # Slow connection (might be having issues)
                    else:
                        quality_indicator = " 🔴"  # Very slow (likely rejecting connections)
                else:
                    if server_name in ["Kezan", "Gurubashi"] and check_duration < 1.0:
                        status_text = "REJECTING"
                        quality_indicator = " 🚫"
                
                log_entry = f"[{current_time}] {server_name}: {status_text}{quality_indicator} ⚡"
                
            elif server_name == "Game Client" and is_up:
                # Special handling for Game Client - only log meaningful updates
                if hasattr(self.server_cards[server_name], 'last_comparison') and self.server_cards[server_name].last_comparison:
                    comparison = self.server_cards[server_name].last_comparison
                    status = comparison["status"]
                    version = comparison.get('version', 'unknown')
                    
                    # Only log if comparison status changed
                    current_comparison_status = f"{status}_{version}"
                    if last_logged_status != current_comparison_status:
                        should_log = True
                        if status == "up_to_date":
                            log_entry = f"[{current_time}] Game Client: ✅ Up to date with {version}"
                        elif status == "outdated":
                            log_entry = f"[{current_time}] Game Client: 🆙 Update available to {version}"
                        elif status == "incomplete":
                            log_entry = f"[{current_time}] Game Client: ❌ Missing files for {version}"
                        else:
                            log_entry = f"[{current_time}] Game Client: ❓ Status unknown for {version}"
                        
                        self.last_status_log[server_name] = current_comparison_status
            
            elif not is_up and server_name in ["Auth", "Kezan", "Gurubashi"]:
                # For server offline events, only log once per offline period
                if last_logged_status != "offline":
                    should_log = True
                    if status_text == "REJECTING":
                        log_entry = f"[{current_time}] {server_name}: 🚫 Rejecting connections"
                    elif status_text == "TIMEOUT":
                        log_entry = f"[{current_time}] {server_name}: ⏱️ Connection timeout"
                    else:
                        log_entry = f"[{current_time}] {server_name}: ❌ Offline"
                    
                    self.last_status_log[server_name] = "offline"
            
            if should_log and log_entry:
                self.add_to_log(log_entry)
                if status_changed:
                    self.last_status_log[server_name] = "online" if is_up else "offline"
            
            if status_changed and is_up and check_duration > 2.0 and server_name in ["Kezan", "Gurubashi"]:
                self.add_to_log(f"⚠️ {server_name} online but very slow response - likely rejecting connections")
            elif status_changed and not is_up and status_text == "REJECTING" and server_name in ["Kezan", "Gurubashi"]:
                self.add_to_log(f"🚫 {server_name} appears to be rejecting game connections")
            
            if self.should_send_notification(server_name, is_up, status_changed):
                # Play different sounds based on status
                if is_up:
                    # Server UP: Play user's chosen sound
                    threading.Thread(target=self.play_sound, daemon=True).start()
                else:
                    # Server DOWN: Play Windows default sound
                    threading.Thread(target=self.play_system_sound_only, daemon=True).start()
                
                status_word = "UP" if is_up else "DOWN"
                auth_status = "Auth online" if self.is_auth_server_online() else "Auth offline"
                
                if status_text == "REJECTING":
                    quality_note = " (rejecting connections)"
                elif is_up and check_duration > 1.5:
                    quality_note = " (slow response - possible issues)"
                else:
                    quality_note = ""
                    
                self.add_to_log(f"🔔 Alert: {server_name} is {status_word} ({auth_status}){quality_note}")
                
            elif status_changed and server_name in ["Kezan", "Gurubashi"]:
                # Additional context for non-notified status changes
                if not self.is_auth_server_online():
                    self.add_to_log(f"⚠️ {server_name} status changed but Auth offline - no alert")
                elif status_text == "REJECTING":
                    self.add_to_log(f"🚫 {server_name} is rejecting connections - no alert sent")
                elif not self.sound_notifications_enabled:
                    self.add_to_log(f"🔇 {server_name} status changed but notifications disabled")
            
            # Auto-actions only trigger when servers come UP (not down)
            if status_changed and is_up and server_name in ["Kezan", "Gurubashi"] and status_text != "REJECTING":
                if self.server_cards[server_name].enabled_cb.isChecked():
                    if self.auto_action_mode == "launch_and_focus":
                        self.launch_client()
                        QTimer.singleShot(2000, self.bring_client_to_front)
                    elif self.auto_action_mode == "focus_existing":
                        self.bring_client_to_front()
    
    def update_runtime_display(self):
        """Update runtime display (placeholder for potential global stats)"""
        # Could add global runtime stats here if needed
        pass
    

    def browse_executable(self):
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
            self.user_settings.set("client_executable_path", file_path)
            
            # Only try to auto-detect if no client directory is set OR if current directory was auto-detected
            if "Game Client" in self.server_cards:
                manifest_card = self.server_cards["Game Client"]
                
                # Check if user has manually set a client directory
                if not manifest_card.client_directory or not manifest_card.client_directory_is_manual:
                    # No manual directory set (or current was auto-detected) - try auto-detection from executable path
                    auto_detected = manifest_card.set_client_directory(file_path)
                    if auto_detected:
                        self.add_to_log(f"🔍 Auto-detected client directory from executable path")
                    else:
                        self.add_to_log(f"💡 Could not auto-detect client directory - use '📁 Set Client Dir' button if needed")
                else:
                    # User has manually set directory - don't override it!
                    manual_dir = os.path.basename(manifest_card.client_directory)
                    self.add_to_log(f"📁 Keeping manually set client directory: {manual_dir}")
                    self.add_to_log(f"💡 Note: Launch executable and game directory can be separate")
    
    def launch_client(self):
        if not self.client_executable_path:
            self.add_to_log("❌ No client executable selected!")
            return False
        
        if not os.path.exists(self.client_executable_path):
            self.add_to_log("❌ Selected executable not found!")
            return False
        
        filename = os.path.basename(self.client_executable_path)
        
        # Check client update status before launching
        self.check_client_update_status_before_launch()
        
        # Check if client is already running
        try:
            if self.is_client_already_running():
                self.add_to_log(f"⚠️ {filename} is already running - focusing existing window instead")
                
                # Try to bring existing window to front
                success = self.bring_client_to_front()
                if success:
                    self.add_to_log(f"✅ Focused existing {filename} window")
                else:
                    self.add_to_log(f"❓ Could not focus existing window - it may be minimized")
                
                return True  # Consider this a success since client is running
        except Exception as e:
            # If process checking fails, just proceed with launch
            self.add_to_log(f"🔍 Could not check for existing processes - launching anyway")
        
        # Client not running (or check failed) - launch new instance
        try:
            # Create process without showing console window
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            subprocess.Popen(
                [self.client_executable_path],
                startupinfo=startupinfo
            )
            self.add_to_log(f"🚀 Launched: {filename}")
            return True
        except Exception as e:
            self.add_to_log(f"❌ Error launching client: {e}")
            return False

    def test_launch_client(self):
        if not self.client_executable_path:
            self.add_to_log("💡 Select a client executable first using the 'Browse' button")
            return
        
        filename = os.path.basename(self.client_executable_path)
        
        # Check update status first
        self.check_client_update_status_before_launch()
        
        # Show current status
        try:
            if self.is_client_already_running():
                self.add_to_log(f"🔍 {filename} is currently running")
            else:
                self.add_to_log(f"🔍 {filename} is not currently running")
        except Exception as e:
            self.add_to_log(f"🔍 Could not detect process status - will attempt launch anyway")
        
        # Proceed with launch
        self.launch_client()
    
    def update_client_button_states(self):
        has_client = bool(self.client_executable_path)
        self.test_launch_btn.setEnabled(has_client)
        
        if hasattr(self, 'launch_and_focus_cb'):
            self.launch_and_focus_cb.setEnabled(has_client)
            if not has_client:
                self.launch_and_focus_cb.setStyleSheet("color: #666666;")
            else:
                self.launch_and_focus_cb.setStyleSheet("color: #ffffff;")
    
    def bring_client_to_front(self):
        # Check update status when focusing existing client
        self.check_client_update_status_before_launch()
        
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
                        
                        # Exclude common non-game applications
                        excluded_keywords = [
                            "Monitor", "Chrome", "Firefox", "Edge", "Browser", "Discord", 
                            "Visual Studio", "Notepad", "Calculator", "Task Manager",
                            "File Explorer", "Windows Security", "Settings", "Steam"
                        ]
                        
                        if any(keyword.lower() in window_title.lower() for keyword in excluded_keywords):
                            return True
                        
                        # Priority search terms
                        target_keywords = []
                        
                        # Add executable name if selected (highest priority)
                        if self.client_executable_path:
                            exe_name = os.path.splitext(os.path.basename(self.client_executable_path))[0]
                            target_keywords.append(exe_name)
                        
                        # Add Project Epoch specific keywords
                        target_keywords.extend([
                            "Project Epoch",
                            "Project-Epoch", 
                            "World of Warcraft", 
                            "WoW"
                        ])
                        
                        # Check if window title matches any target keywords
                        for keyword in target_keywords:
                            if keyword.lower() in window_title.lower():
                                # Additional validation for Project Epoch to avoid Discord/browser tabs
                                if "project" in window_title.lower() and "epoch" in window_title.lower():
                                    excluded_in_title = ["discord", "chrome", "firefox", "edge", "browser", "tab"]
                                    if any(excluded.lower() in window_title.lower() for excluded in excluded_in_title):
                                        continue  # Skip this window
                                
                                try:
                                    # Multi-method window focusing for better reliability
                                    user32.SetForegroundWindow(hwnd)
                                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                                    user32.SetActiveWindow(hwnd)
                                    user32.BringWindowToTop(hwnd)
                                    
                                    found_window = True
                                    self.add_to_log(f"✅ Focused window: {window_title}")
                                    return False  # Stop enumeration
                                except Exception as e:
                                    self.add_to_log(f"❌ Failed to focus '{window_title}': {e}")
                                    continue
                
                return True  # Continue enumeration
            
            # Enumerate all windows
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
            
            if not found_window:
                self.add_to_log("❓ No Project Epoch/WoW windows found to focus")
            
            return found_window
            
        except Exception as e:
            self.add_to_log(f"❌ Error bringing client to front: {e}")
            return False
    
    def test_focus_client(self):
        self.add_to_log("🔍 Testing window focus...")
        
        # Check update status when testing focus
        self.check_client_update_status_before_launch()
        
        # First check if client is running
        if self.client_executable_path:
            filename = os.path.basename(self.client_executable_path)
            try:
                if self.is_client_already_running():
                    self.add_to_log(f"✅ {filename} is running - attempting to focus...")
                else:
                    self.add_to_log(f"⚠️ {filename} doesn't appear to be running")
            except Exception:
                self.add_to_log(f"🔍 Could not detect if {filename} is running")
        
        success = self.bring_client_to_front()
        if not success:
            self.add_to_log("💡 Tip: Make sure Project Epoch is running first!")

    def check_client_update_status_before_launch(self):
        """Check if client needs updating before launch/focus operations"""
        try:
            # Only check if we have the Game Client manifest card and it's monitoring
            if "Game Client" not in self.server_cards:
                return
            
            manifest_card = self.server_cards["Game Client"]
            
            # Only check if we have a client directory set and recent manifest data
            if not manifest_card.client_directory or not manifest_card.last_manifest_data:
                return
            
            # Only check if manifest monitoring is enabled
            if not manifest_card.enabled_cb.isChecked():
                return
            
            # Check if we have recent comparison data
            if not manifest_card.last_comparison:
                return
            
            comparison = manifest_card.last_comparison
            status = comparison.get("status", "unknown")
            version = comparison.get("version", "unknown")
            
            # Only log if client is not up-to-date
            if status == "outdated":
                files_outdated = comparison.get("files_outdated", 0)
                self.add_to_log(f"🆙 Client update available to {version} ({files_outdated} files need updating)")
                
                # Play system sound for update notification (no custom sound for this)
                if self.sound_notifications_enabled:
                    threading.Thread(target=self.play_system_sound_only, daemon=True).start()
                    
            elif status == "incomplete":
                files_missing = comparison.get("files_missing", 0)
                self.add_to_log(f"❌ Client is missing {files_missing} critical files for {version}")
                
                # Play system sound for missing files warning
                if self.sound_notifications_enabled:
                    threading.Thread(target=self.play_system_sound_only, daemon=True).start()
            
            elif status == "up_to_date":
                # Only log this occasionally to avoid spam, or if explicitly requested via test launch
                if hasattr(self, '_last_update_check_log'):
                    import time
                    if time.time() - self._last_update_check_log < 60:  # Don't spam within 60 seconds
                        return
                
                self._last_update_check_log = time.time()
                self.add_to_log(f"✅ Client is up-to-date with {version}")
            
            # For unknown status, don't log anything to avoid confusion
            
        except Exception as e:
            # Silently fail - update checking shouldn't break launch functionality
            pass

    def _check_unix_processes(self, exe_name):
        """Unix/Linux process checking using ps command"""
        try:
            result = subprocess.run(
                ['ps', '-A', '-o', 'comm='],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                process_names = result.stdout.lower().split('\n')
                exe_base = exe_name.replace('.exe', '').lower()
                
                return any(exe_base in proc_name for proc_name in process_names)
            else:
                return False
            
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False
        
    def _check_windows_processes(self, exe_name):
        """Windows-specific process checking using built-in tasklist command"""
        try:
            # Use tasklist with filter - this is built into Windows!
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {exe_name}'],
                capture_output=True,
                text=True,
                shell=False,  # Don't use shell for better security
                timeout=5,    # Increased timeout for slower systems
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # Hide console window
            )
            
            if result.returncode == 0:
                output = result.stdout.lower()
                # tasklist returns the process if found, otherwise shows "no tasks running"
                return exe_name.lower() in output and "no tasks are running" not in output
            else:
                return False
            
        except subprocess.TimeoutExpired:
            self.add_to_log("⚠️ Process check timed out")
            return False
        except FileNotFoundError:
            self.add_to_log("⚠️ tasklist command not found")
            return False
        except Exception as e:
            return False
        
    def is_client_already_running(self):
        try:
            if not self.client_executable_path:
                return False
            
            exe_name = os.path.basename(self.client_executable_path).lower()
            
            # Use built-in Windows commands (works in standalone exe too!)
            if sys.platform == "win32":
                return self._check_windows_processes(exe_name)
            else:
                # For non-Windows systems, use ps command
                return self._check_unix_processes(exe_name)
            
        except Exception as e:
            # If checking fails, assume not running to avoid blocking launch
            self.add_to_log(f"🔍 Process detection failed, proceeding with launch")
            return False
    
    def update_auto_action_checkboxes(self):
        self.no_action_cb.setChecked(self.auto_action_mode == "none")
        self.focus_existing_cb.setChecked(self.auto_action_mode == "focus_existing")
        self.launch_and_focus_cb.setChecked(self.auto_action_mode == "launch_and_focus")
    
    def toggle_no_action(self, checked):
        if checked:
            self.auto_action_mode = "none"
            self.focus_existing_cb.setChecked(False)
            self.launch_and_focus_cb.setChecked(False)
            self.user_settings.set("auto_action_mode", "none")
    
    def toggle_focus_existing(self, checked):
        if checked:
            self.auto_action_mode = "focus_existing"
            self.no_action_cb.setChecked(False)
            self.launch_and_focus_cb.setChecked(False)
            self.user_settings.set("auto_action_mode", "focus_existing")
    
    def toggle_launch_and_focus(self, checked):
        if checked:
            if not self.client_executable_path:
                self.add_to_log("Please select a client executable first!")
                self.launch_and_focus_cb.setChecked(False)
                return
            
            self.auto_action_mode = "launch_and_focus"
            self.no_action_cb.setChecked(False)
            self.focus_existing_cb.setChecked(False)
            self.user_settings.set("auto_action_mode", "launch_and_focus")
    
    def toggle_sound_notifications(self, checked):
        self.sound_notifications_enabled = checked
        self.user_settings.set("sound_notifications_enabled", checked)

    def test_play_sound(self):
        self.add_to_log("Testing sound...")
        threading.Thread(target=self.play_sound, daemon=True).start()
    
    def play_system_sound(self):
        """Play system notification sound"""
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            elif sys.platform == "darwin":
                os.system("afplay /System/Library/Sounds/Glass.aiff")
            else:
                os.system("paplay /usr/share/sounds/alsa/Front_Left.wav 2>/dev/null || echo -e '\a'")
        except Exception as e:
            print(f"System sound error: {e}")
    
    def play_custom_sound_file(self, sound_path):
        try:
            volume_factor = self.sound_volume / 100.0
            
            if AUDIO_LIB == "playsound3":
                # Try pygame for volume control first
                if volume_factor < 1.0:
                    try:
                        import pygame
                        if not pygame.mixer.get_init():
                            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
                        
                        # Load and play with volume control
                        sound = pygame.mixer.Sound(sound_path)
                        sound.set_volume(volume_factor)
                        sound.play()
                        return
                    except (ImportError, pygame.error):
                        pass  # Fall back to playsound3
                
                # Fallback to playsound3 (no volume control)
                playsound(sound_path)
                
            elif AUDIO_LIB == "pygame":
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
                
                # Use Sound for better volume control instead of music
                try:
                    sound = pygame.mixer.Sound(sound_path)
                    sound.set_volume(volume_factor)
                    sound.play()
                except pygame.error:
                    # Fallback to music if Sound fails
                    pygame.mixer.music.set_volume(volume_factor)
                    pygame.mixer.music.load(sound_path)
                    pygame.mixer.music.play()
                    
        except Exception as e:
            print(f"Custom sound playback error: {e}")
            # Fallback to system sound
            self.play_system_sound()
    
    def play_sound(self):
        """Play notification sound with volume control"""
        if not self.sound_notifications_enabled:
            return
            
        sound_path = self.get_sound_path(self.selected_sound)
        
        if sound_path and os.path.exists(sound_path) and HAS_AUDIO:
            try:
                threading.Thread(target=lambda: self.play_custom_sound_file(sound_path), daemon=True).start()
            except Exception as e:
                print(f"Custom sound error: {e}")
                self.play_system_sound()
        else:
            self.play_system_sound()
    
    def show_notification(self, title, message):
        """Show notification with sound only - CLEANED UP"""
        try:
            if self.sound_notifications_enabled:
                threading.Thread(target=self.play_sound, daemon=True).start()
        except Exception as e:
            print(f"Sound notification error: {e}")
    
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

    def start_manifest_monitoring(self):
            """Start manifest monitoring thread"""
            try:
                if self.manifest_thread:
                    old_thread = self.manifest_thread
                    if old_thread.running:
                        old_thread.stop()
                        self.threads_to_cleanup.append(old_thread)
                        QApplication.processEvents()
                
                # Create new manifest thread
                self.manifest_thread = ManifestMonitorThread()
                self.manifest_thread.set_interval(self.manifest_check_interval)
                self.manifest_thread.set_user_settings(self.user_settings)
                
                # Connect signals
                self.manifest_thread.status_update.connect(self.on_manifest_status_update)
                self.manifest_thread.version_changed.connect(self.on_build_version_changed)
                
                self.manifest_thread.running = True
                self.manifest_thread.start()
                
                return True
                
            except Exception as e:
                self.add_to_log(f"Error starting manifest monitoring: {e}")
                return False

    def stop_manifest_monitoring(self):
        """Non-blocking manifest thread stopping"""
        if self.manifest_thread and self.manifest_thread.running:
            self.manifest_thread.stop()
            self.threads_to_cleanup.append(self.manifest_thread)
            self.manifest_thread = None
            return True
        return False

    def on_manifest_status_update(self, server_name, is_up, check_duration, manifest_data):
        if "Game Client" in self.server_cards:
            card = self.server_cards["Game Client"]
            
            # Store old state to detect changes
            old_is_up = card.is_up
            old_version = getattr(card, 'current_version', None)
            old_comparison_status = None
            
            if hasattr(card, 'last_comparison') and card.last_comparison:
                old_comparison_status = f"{card.last_comparison['status']}_{card.last_comparison.get('version', 'unknown')}"
            
            card.update_manifest_status(is_up, check_duration, manifest_data)
            
            # Determine what changed and if we should log
            current_time = datetime.now().strftime("%H:%M:%S")
            should_log = False
            log_entry = ""
            
            # Get last logged status for this server
            last_logged_status = self.last_status_log.get(server_name, "")
            
            if is_up and manifest_data and 'Version' in manifest_data:
                version = manifest_data['Version']
                file_count = len(manifest_data.get('Files', []))
                
                # Check if version changed
                version_changed = old_version != version
                
                if card.client_directory and card.last_comparison:
                    # We have client directory - check comparison results
                    comparison = card.last_comparison
                    status = comparison["status"]
                    current_comparison_status = f"{status}_{version}"
                    
                    # Only log if comparison status actually changed OR version changed
                    if (last_logged_status != current_comparison_status) or version_changed:
                        should_log = True
                        
                        if status == "up_to_date":
                            if version_changed:
                                log_entry = f"[{current_time}] Game Client: ✅ Updated to {version} and verified"
                            else:
                                log_entry = f"[{current_time}] Game Client: ✅ Up to date with {version}"
                        elif status == "outdated":
                            log_entry = f"[{current_time}] Game Client: 🆙 Update available to {version} ({comparison['files_outdated']} files need updating)"
                        elif status == "incomplete":
                            log_entry = f"[{current_time}] Game Client: ❌ Missing {comparison['files_missing']} critical files for {version}"
                        else:
                            log_entry = f"[{current_time}] Game Client: ❓ Cannot determine status for {version}"
                        
                        # Update tracking
                        self.last_status_log[server_name] = current_comparison_status
                        
                else:
                    # No client set - only log if we haven't logged this version yet
                    current_status = f"manifest_only_{version}"
                    if last_logged_status != current_status:
                        should_log = True
                        log_entry = f"[{current_time}] Manifest API: {version} available ({file_count} files) - Set client directory for comparison"
                        self.last_status_log[server_name] = current_status
                        
            elif is_up and manifest_data and 'error' in manifest_data:
                # Error case - only log if error type changed
                error = manifest_data['error']
                error_type = "timeout" if "timeout" in error.lower() else "connection" if "connection" in error.lower() or "ssl" in error.lower() else "format" if "json" in error.lower() else "other"
                
                current_error_status = f"error_{error_type}"
                if last_logged_status != current_error_status:
                    should_log = True
                    log_entry = f"[{current_time}] Manifest API: ❌ {error}"
                    self.last_status_log[server_name] = current_error_status
                    
            elif not is_up:
                # Offline case - only log once per offline period
                offline_status = "timeout" if check_duration > 8 else "offline"
                current_offline_status = f"offline_{offline_status}"
                
                if last_logged_status != current_offline_status:
                    should_log = True
                    status_text = "⏱️ Connection timeout" if check_duration > 8 else "❌ Connection failed"
                    log_entry = f"[{current_time}] Manifest API: {status_text}"
                    self.last_status_log[server_name] = current_offline_status
            
            # Only log if something meaningful changed
            if should_log and log_entry:
                self.add_to_log(log_entry)

    def on_build_version_changed(self, old_version, new_version):
        # This is always worth logging since it's a significant event
        self.add_to_log(f"Game Update Detected: {old_version} → {new_version}")
        
        # Check if client needs updating after version change
        if "Game Client" in self.server_cards:
            manifest_card = self.server_cards["Game Client"]
            if manifest_card.client_directory and manifest_card.last_manifest_data:
                # Re-run comparison with new manifest data
                comparison = manifest_card.local_detector.compare_with_manifest(
                    manifest_card.client_directory, 
                    manifest_card.last_manifest_data
                )
                
                if comparison["status"] == "outdated":
                    self.add_to_log(f"🔄 Your client needs updating to {new_version}")
                elif comparison["status"] == "up_to_date":
                    self.add_to_log(f"✅ Your client is already updated to {new_version}")
            else:
                self.add_to_log(f"💡 Set client directory to check if update is needed")
        
        # Play Windows default sound for manifest updates
        if self.sound_notifications_enabled:
            threading.Thread(target=self.play_system_sound_only, daemon=True).start()
            self.add_to_log(f"🔔 Update notification played")
        
        # Clear the tracking for Game Client since version changed
        if "Game Client" in self.last_status_log:
            del self.last_status_log["Game Client"]
        
        # Version history tracking (minimal logging)
        version_info = self.user_settings.get_version_change_info()
        history_count = len(version_info.get('history', []))
        if history_count > 1:  # Only show count if we have multiple tracked versions
            self.add_to_log(f"📈 Version change #{history_count} tracked")

    def on_server_monitoring_toggled(self, server_name, enabled):
        # Handle manifest monitoring specially
        if server_name == "Game Client":
            if enabled:
                self.server_cards[server_name].set_to_starting_state()
                if self.start_manifest_monitoring():
                    self.add_to_log(f"Starting manifest monitoring...")
                else:
                    self.add_to_log(f"Failed to start manifest monitoring")
                    self.server_cards[server_name].set_to_enabled_state()
            else:
                self.server_cards[server_name].set_to_disabled_state()
                self.stop_manifest_monitoring()
                self.add_to_log(f"Stopping manifest monitoring...")
            return
        
        if not self.monitor_threads:
            return
        
        if enabled:
            self.server_cards[server_name].set_to_starting_state()
            
            if server_name not in self.monitor_threads or not self.monitor_threads[server_name].running:
                if self.start_single_server_monitoring(server_name):
                    self.add_to_log(f"Starting monitoring for {server_name}...")
                else:
                    self.add_to_log(f"Failed to start monitoring for {server_name}")
                    self.server_cards[server_name].set_to_enabled_state()
            else:
                self.add_to_log(f"{server_name} is already being monitored")
                self.server_cards[server_name].set_to_enabled_state()
        else:
            self.server_cards[server_name].set_to_disabled_state()
            
            if server_name in self.monitor_threads and self.monitor_threads[server_name].running:
                self.stop_single_server_monitoring(server_name)
                self.add_to_log(f"Stopping monitoring for {server_name}...")

    def start_all_monitoring(self):
        if self.start_time is None:
            self.start_time = datetime.now()
        
        self.detect_active_server_connections()
        
        enabled_servers = []
        
        for server_name, card in self.server_cards.items():
            if server_name == "Game Client":
                continue
                
            if card.enabled_cb.isChecked():
                card.set_to_starting_state()
                enabled_servers.append(server_name)
                self.start_single_server_monitoring(server_name)
        
        if self.server_cards["Game Client"].enabled_cb.isChecked():
            self.server_cards["Game Client"].set_to_starting_state()
            if self.start_manifest_monitoring():
                enabled_servers.append("Game Client")
        
        if enabled_servers:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.ui_timer.start(1000)
            
            servers_list = ", ".join(enabled_servers)
            self.add_to_log(f"Started monitoring: {servers_list}")
            
            # Clear previous status tracking
            self.last_status_log.clear()
        else:
            self.add_to_log("No servers enabled for monitoring!")

    def stop_all_monitoring(self):
        stopped_servers = []
        
        # Signal all threads to stop (non-blocking)
        for server_name, thread in list(self.monitor_threads.items()):
            if thread.running:
                thread.stop()
                stopped_servers.append(server_name)
                self.threads_to_cleanup.append(thread)
        
        self.monitor_threads.clear()
        
        # Stop manifest thread (non-blocking)
        if self.manifest_thread and self.manifest_thread.running:
            self.manifest_thread.stop()
            self.threads_to_cleanup.append(self.manifest_thread)
            stopped_servers.append("Game Client")
            self.manifest_thread = None
        
        # Reset all server cards
        for card in self.server_cards.values():
            card.is_monitoring_disabled = False
            card.is_starting = False
            card.status_text.setText("STOPPED")
            card.status_text.setStyleSheet("font-weight: bold; font-size: 12px; color: #ffab40;")
            card.status_indicator.setStyleSheet("color: #757575; font-size: 20px;")
            card.setStyleSheet("""
                QWidget {
                    background-color: #404040;
                    border: 2px solid #555555;
                    border-radius: 8px;
                    margin: 2px;
                }
            """)
        
        # Update UI state
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.ui_timer.stop()
        
        if stopped_servers:
            servers_list = ", ".join(stopped_servers)
            self.add_to_log(f"Stopped monitoring: {servers_list}")
        else:
            self.add_to_log("All monitoring stopped")
        
        # Clear status tracking
        self.last_status_log.clear()

class AdvancedSettingsDialog(QDialog):
    """Advanced settings management dialog"""
    
    def __init__(self, user_settings, parent=None):
        super().__init__(parent)
        self.user_settings = user_settings
        self.setWindowTitle("Advanced Settings Management")
        self.setModal(True)
        self.resize(600, 500)
        
        self.init_ui()
        self.load_current_settings()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Settings Location Group
        location_group = QGroupBox("Settings Storage Location")
        location_layout = QVBoxLayout(location_group)
        
        self.auto_radio = QRadioButton("Auto-detect best location")
        self.portable_radio = QRadioButton("Portable (next to application)")
        self.appdata_radio = QRadioButton("User folder (AppData/config)")
        self.custom_radio = QRadioButton("Custom location:")
        
        self.custom_path_edit = QLineEdit()
        self.custom_path_edit.setEnabled(False)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setEnabled(False)
        self.browse_btn.clicked.connect(self.browse_custom_location)
        
        custom_row = QHBoxLayout()
        custom_row.addWidget(self.custom_path_edit)
        custom_row.addWidget(self.browse_btn)
        
        # Connect radio buttons
        self.custom_radio.toggled.connect(self.on_custom_radio_toggled)
        
        location_layout.addWidget(self.auto_radio)
        location_layout.addWidget(self.portable_radio)
        location_layout.addWidget(self.appdata_radio)
        location_layout.addWidget(self.custom_radio)
        location_layout.addLayout(custom_row)
        
        layout.addWidget(location_group)
        
        # Settings Behavior Group
        behavior_group = QGroupBox("Settings Behavior")
        behavior_layout = QVBoxLayout(behavior_group)
        
        self.auto_save_cb = QCheckBox("Automatically save settings when changed")
        self.auto_save_cb.setChecked(True)
        
        behavior_layout.addWidget(self.auto_save_cb)
        layout.addWidget(behavior_group)
        
        # Current Status Group
        status_group = QGroupBox("Current Status")
        status_layout = QVBoxLayout(status_group)
        
        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(120)
        self.status_text.setReadOnly(True)
        status_layout.addWidget(self.status_text)
        
        # Refresh status button
        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.clicked.connect(self.refresh_status)
        status_layout.addWidget(refresh_btn)
        
        layout.addWidget(status_group)
        
        # Action Buttons Group
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        # Clear cache button
        clear_cache_btn = QPushButton("🗑️ Clear All Settings Cache")
        clear_cache_btn.clicked.connect(self.clear_all_cache)
        clear_cache_btn.setStyleSheet("QPushButton { background-color: #d32f2f; } QPushButton:hover { background-color: #f44336; }")
        
        # Manual save button  
        manual_save_btn = QPushButton("💾 Save Settings Now")
        manual_save_btn.clicked.connect(self.manual_save)
        
        actions_layout.addWidget(manual_save_btn)
        actions_layout.addWidget(clear_cache_btn)
        layout.addWidget(actions_group)
        
        # Dialog buttons
        button_layout = QHBoxLayout()
        
        apply_btn = QPushButton("Apply Changes")
        apply_btn.clicked.connect(self.apply_changes)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(apply_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def load_current_settings(self):
        """Load current settings into the dialog"""
        location = self.user_settings.get("settings_location", "auto")
        
        if location == "auto":
            self.auto_radio.setChecked(True)
        elif location == "portable":
            self.portable_radio.setChecked(True)
        elif location == "appdata":
            self.appdata_radio.setChecked(True)
        elif location == "custom":
            self.custom_radio.setChecked(True)
            custom_path = self.user_settings.get("custom_settings_path", "")
            self.custom_path_edit.setText(custom_path)
        
        self.auto_save_cb.setChecked(self.user_settings.get("auto_save_settings", True))
        self.refresh_status()
    
    def on_custom_radio_toggled(self, checked):
        """Enable/disable custom path controls"""
        self.custom_path_edit.setEnabled(checked)
        self.browse_btn.setEnabled(checked)
    
    def browse_custom_location(self):
        """Browse for custom settings location"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose Settings File Location",
            "monitor_settings.json",
            "JSON files (*.json);;All files (*.*)"
        )
        if file_path:
            self.custom_path_edit.setText(file_path)
    
    def refresh_status(self):
        """Refresh the status display"""
        locations = self.user_settings.get_all_settings_locations()
        
        status_lines = []
        status_lines.append(f"📁 Current settings file: {locations['current']['path']}")
        status_lines.append(f"✅ Current file exists: {'Yes' if locations['current']['exists'] else 'No'}")
        status_lines.append(f"✏️ Current location writable: {'Yes' if locations['current']['writable'] else 'No'}")
        status_lines.append("")
        
        status_lines.append("📍 Available locations:")
        for key, info in locations.items():
            if key != "current":
                status_icon = "✅" if info['writable'] else "❌"
                exists_icon = "📄" if info['exists'] else "➖"
                status_lines.append(f"  {status_icon} {exists_icon} {info['description']}")
                status_lines.append(f"      {info['path']}")
        
        self.status_text.setPlainText("\n".join(status_lines))
    
    def apply_changes(self):
        """Apply the settings changes"""
        try:
            # Determine new location preference
            if self.auto_radio.isChecked():
                new_location = "auto"
                custom_path = ""
            elif self.portable_radio.isChecked():
                new_location = "portable"
                custom_path = ""
            elif self.appdata_radio.isChecked():  
                new_location = "appdata"
                custom_path = ""
            elif self.custom_radio.isChecked():
                new_location = "custom"
                custom_path = self.custom_path_edit.text().strip()
                if not custom_path:
                    QMessageBox.warning(self, "Invalid Path", "Please specify a custom path or choose a different option.")
                    return
            
            # Update auto-save preference
            self.user_settings.set("auto_save_settings", self.auto_save_cb.isChecked())
            
            # Change location if needed
            current_location = self.user_settings.get("settings_location", "auto")
            current_custom = self.user_settings.get("custom_settings_path", "")
            
            if new_location != current_location or custom_path != current_custom:
                old_path = self.user_settings.change_settings_location(new_location, custom_path)
                
                if old_path and os.path.exists(old_path):
                    # Ask if user wants to delete old settings file
                    reply = QMessageBox.question(
                        self, 
                        "Delete Old Settings?", 
                        f"Settings have been moved to the new location.\n\nDelete the old settings file?\n{old_path}",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    
                    if reply == QMessageBox.StandardButton.Yes:
                        try:
                            os.remove(old_path)
                            QMessageBox.information(self, "Success", "Old settings file deleted successfully!")
                        except Exception as e:
                            QMessageBox.warning(self, "Error", f"Could not delete old settings file:\n{e}")
            
            QMessageBox.information(self, "Settings Applied", "Settings have been applied successfully!")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply settings:\n{e}")
    
    def clear_all_cache(self):
        """Clear all settings cache"""
        reply = QMessageBox.question(
            self,
            "Clear All Settings?",
            "This will delete ALL settings files from ALL locations and reset to defaults.\n\nThis cannot be undone. Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                cleared_files = self.user_settings.clear_all_cache()
                if cleared_files:
                    files_list = "\n".join(cleared_files)
                    QMessageBox.information(self, "Cache Cleared", f"Deleted settings files:\n\n{files_list}")
                else:
                    QMessageBox.information(self, "Cache Cleared", "No settings files found to delete.")
                
                # Refresh status
                self.refresh_status()
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear cache:\n{e}")
    
    def manual_save(self):
        """Force save current settings"""
        try:
            self.user_settings.manual_save()
            QMessageBox.information(self, "Settings Saved", f"Settings saved to:\n{self.user_settings.current_settings_path}")
            self.refresh_status()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")

class ManifestMonitorThread(QThread):
    status_update = pyqtSignal(str, bool, float, dict)  # server_name, is_up, check_duration, manifest_data
    version_changed = pyqtSignal(str, str)  # old_version, new_version
    
    def __init__(self, manifest_url="https://updater.project-epoch.net/api/v2/manifest?environment=production", parent=None):
        super().__init__(parent)
        self.manifest_url = manifest_url
        self.server_name = "Game Client"
        self.running = False
        self.check_interval = 30  # Default 30 seconds
        self._stop_event = threading.Event()
        self.last_known_version = None
        self.user_settings = None  # Will be set by parent

    def __del__(self):
        try:
            self.stop()
            if hasattr(self, '_stop_event'):
                self._stop_event.set()
        except:
            pass  # Ignore errors during cleanup
        
    def run(self):
        while self.running and not self._stop_event.is_set():
            start_time = time.time()
            is_up, manifest_data = self.check_manifest()
            check_duration = time.time() - start_time
            
            self.status_update.emit(self.server_name, is_up, check_duration, manifest_data)
            
            # Check for version changes
            if is_up and manifest_data and 'Version' in manifest_data:
                current_version = manifest_data['Version']
                
                if self.user_settings:
                    old_version = self.user_settings.update_build_version(current_version)
                    
                    # Emit version change signal if version actually changed
                    if old_version and old_version != current_version:
                        self.version_changed.emit(old_version, current_version)
                
                self.last_known_version = current_version
            
            remaining_sleep = max(0, self.check_interval - check_duration)
            
            if remaining_sleep > 0:
                self._stop_event.wait(remaining_sleep)
    
    def check_manifest(self):
        """Check the manifest URL and return status + data"""
        try:
            # Add headers to mimic a real browser request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache'
            }
            
            response = requests.get(
                self.manifest_url, 
                timeout=8,  # Reduced from 10 to 8 seconds
                headers=headers,
                verify=True  # Enable SSL verification
            )
            
            if response.status_code == 200:
                try:
                    manifest_data = response.json()
                    
                    required_fields = ['Version', 'Files', 'Uid']
                    if all(field in manifest_data for field in required_fields):
                        manifest_data['_debug'] = {
                            'response_time': response.elapsed.total_seconds(),
                            'status_code': response.status_code,
                            'content_length': len(response.content)
                        }
                        return True, manifest_data
                    else:
                        missing_fields = [f for f in required_fields if f not in manifest_data]
                        return False, {"error": f"Invalid manifest format - missing: {', '.join(missing_fields)}"}
                        
                except json.JSONDecodeError as e:
                    return False, {"error": f"JSON decode error: {str(e)[:50]}"}
            else:
                return False, {"error": f"HTTP {response.status_code}: {response.reason}"}
                
        except requests.exceptions.Timeout:
            return False, {"error": "Request timeout (8s limit exceeded)"}
        except requests.exceptions.SSLError as e:
            return False, {"error": f"SSL error: {str(e)[:50]}"}
        except requests.exceptions.ConnectionError as e:
            return False, {"error": f"Connection failed: {str(e)[:50]}"}
        except requests.exceptions.RequestException as e:
            return False, {"error": f"Request error: {str(e)[:50]}"}
        except Exception as e:
            return False, {"error": f"Unexpected error: {str(e)[:50]}"}
    
    def set_interval(self, interval):
        self.check_interval = max(15, min(300, interval))  # Between 15s and 5min
    
    def set_user_settings(self, user_settings):
        self.user_settings = user_settings
    
    def stop(self):
        self.running = False
        if hasattr(self, '_stop_event'):
            self._stop_event.set()

class ManifestServerCard(ServerCard):
    """Special server card for manifest/version monitoring with local file comparison"""
    
    def __init__(self, parent=None):
        # Initialize with manifest-specific parameters
        super().__init__("Game Client", "Manifest", 443, parent)
        self.current_version = None
        self.last_manifest_data = {}
        self.local_detector = LocalClientDetector()
        self.client_directory = None
        self.client_directory_is_manual = False
        self.last_comparison = None
        
        # Update the checkbox text for manifest monitoring
        self.enabled_cb.setText("Monitor game updates")
        
        # Update port label to show URL instead of port
        self.port_label.setText("updater.project-epoch.net")
        
        # Add version display
        self.version_label = QLabel("Version: Unknown")
        self.version_label.setStyleSheet("font-size: 10px; color: #64b5f6; font-weight: bold;")
        
        # Add client status display
        self.client_status_label = QLabel("Client: Not Set")
        self.client_status_label.setStyleSheet("font-size: 9px; color: #999999;")
        
        # Add browse button for client directory
        self.browse_client_btn = QPushButton("📁 Set Client Dir")
        self.browse_client_btn.setStyleSheet("""
            QPushButton {
                font-size: 8px;
                padding: 2px 4px;
                max-height: 18px;
                background-color: #505050;
                border: 1px solid #666666;
            }
            QPushButton:hover {
                background-color: #606060;
            }
        """)
        self.browse_client_btn.clicked.connect(self.browse_client_directory)
        self.browse_client_btn.setToolTip("Browse for Project Epoch game folder")
        
        # Insert widgets before the checkbox
        layout = self.layout()
        layout.insertWidget(layout.count() - 1, self.version_label)
        
        # Create horizontal layout for client status and browse button
        client_row = QHBoxLayout()
        client_row.setContentsMargins(0, 0, 0, 0)
        client_row.addWidget(self.client_status_label)
        client_row.addWidget(self.browse_client_btn)
        client_row.setStretch(0, 1)
        
        # Create widget to hold the horizontal layout
        client_widget = QWidget()
        client_widget.setLayout(client_row)
        layout.insertWidget(layout.count() - 1, client_widget)
    
    def browse_client_directory(self):
        """Browse for client directory with option to clear"""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        
        # If directory is already set, ask if they want to browse or clear
        if self.client_directory:
            reply = QMessageBox.question(
                self,
                "Client Directory Options",
                f"Current directory: {os.path.basename(self.client_directory)}\n\nWhat would you like to do?",
                QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Reset | QMessageBox.StandardButton.Cancel
            )
            reply.button(QMessageBox.StandardButton.Open).setText("Browse New")
            reply.button(QMessageBox.StandardButton.Reset).setText("Clear Directory")
            
            if reply == QMessageBox.StandardButton.Reset:
                self.clear_client_directory()
                return
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        
        # Start from current directory if set, otherwise user's home
        start_dir = self.client_directory if self.client_directory else os.path.expanduser('~')
        
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Project Epoch Game Folder", 
            start_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        
        if directory:
            # Mark this as manual directory selection
            self.set_client_directory_path(directory, is_manual=True)
    
    def set_client_directory_path(self, directory_path, is_manual=False):
        """Set client directory directly from path and save to settings"""
        if not directory_path or not os.path.exists(directory_path):
            # Only clear if this directory doesn't exist
            if self.client_directory == directory_path:
                self.client_directory = None
                self.client_directory_is_manual = False
            
            self.client_status_label.setText("Client: Invalid Path")
            self.client_status_label.setStyleSheet("font-size: 9px; color: #f44336;")
            
            # Only clear from settings if this was a manual attempt OR if we're clearing the same path
            # Don't clear manual settings when auto-detection fails!
            if is_manual and hasattr(self.parent(), 'user_settings'):
                self.parent().user_settings.set("manifest_client_directory", "")
                if hasattr(self.parent(), 'add_to_log'):
                    self.parent().add_to_log("⚠️ Invalid directory selected - cleared from settings")
            elif not is_manual and directory_path == self.client_directory:
                # Only clear if we're trying to set the same path that's currently set
                if hasattr(self.parent(), 'user_settings'):
                    self.parent().user_settings.set("manifest_client_directory", "")
            
            return False
        
        # Verify it looks like a Project Epoch directory
        required_files = ["Project-Epoch.exe", "Data"]
        missing_files = [f for f in required_files if not os.path.exists(os.path.join(directory_path, f))]
        
        if missing_files:
            # Only clear if this directory doesn't meet requirements
            if self.client_directory == directory_path:
                self.client_directory = None
                self.client_directory_is_manual = False
            
            missing_str = ", ".join(missing_files)
            self.client_status_label.setText(f"Client: Missing {missing_str}")
            self.client_status_label.setStyleSheet("font-size: 9px; color: #f44336;")
            self.client_status_label.setToolTip(f"This folder is missing: {missing_str}")
            
            # Only clear from settings if this was a manual attempt OR if we're clearing the same path
            if is_manual and hasattr(self.parent(), 'user_settings'):
                self.parent().user_settings.set("manifest_client_directory", "")
                if hasattr(self.parent(), 'add_to_log'):
                    self.parent().add_to_log(f"⚠️ Selected directory is not a valid Project Epoch folder - missing {missing_str}")
            elif not is_manual and directory_path == self.client_directory:
                # Only clear if we're trying to set the same path that's currently set
                if hasattr(self.parent(), 'user_settings'):
                    self.parent().user_settings.set("manifest_client_directory", "")
            
            return False
        
        # Valid directory - set and save to settings
        self.client_directory = directory_path
        self.client_directory_is_manual = is_manual  # Track how this was set
        dir_name = os.path.basename(directory_path)
        self.client_status_label.setText(f"Client: {dir_name}")
        self.client_status_label.setStyleSheet("font-size: 9px; color: #64b5f6; font-weight: bold;")
        self.client_status_label.setToolTip(f"Monitoring: {directory_path}")
        
        # Save to user settings
        if hasattr(self.parent(), 'user_settings'):
            self.parent().user_settings.set("manifest_client_directory", directory_path)
            # Log differently based on how it was set
            if hasattr(self.parent(), 'add_to_log'):
                if is_manual:
                    self.parent().add_to_log(f"📁 Manually set client directory: {dir_name}")
                else:
                    self.parent().add_to_log(f"🔍 Auto-detected client directory: {dir_name}")
        
        # Trigger a re-check if we have manifest data
        if self.last_manifest_data and 'Version' in self.last_manifest_data:
            self.update_manifest_status(self.is_up, 0, self.last_manifest_data)
        
        return True
    
    def clear_client_directory(self):
        """Clear the client directory and remove from settings"""
        self.client_directory = None
        self.client_directory_is_manual = False  # Reset manual flag
        self.client_status_label.setText("Client: Not Set")
        self.client_status_label.setStyleSheet("font-size: 9px; color: #999999;")
        self.client_status_label.setToolTip("Click 'Set Client Dir' to compare with local files")
        
        # Clear from settings
        if hasattr(self.parent(), 'user_settings'):
            self.parent().user_settings.set("manifest_client_directory", "")
            if hasattr(self.parent(), 'add_to_log'):
                self.parent().add_to_log("📂 Client directory cleared")
    
    def set_client_directory(self, client_executable_path):
        """Set the client directory from executable path (AUTO-DETECTION method)"""
        detected_dir = self.local_detector.detect_client_directory(client_executable_path)
        if detected_dir:
            # Mark this as auto-detected (not manual)
            return self.set_client_directory_path(detected_dir, is_manual=False)
        else:
            # Don't clear existing manual directory when auto-detection fails!
            if not self.client_directory_is_manual:
                self.client_directory = None
                self.client_directory_is_manual = False
                
                if client_executable_path:
                    exe_name = os.path.basename(client_executable_path)
                    self.client_status_label.setText(f"Client: {exe_name} (wrong folder?)")
                    self.client_status_label.setStyleSheet("font-size: 9px; color: #ff9800;")
                    self.client_status_label.setToolTip("Executable found but not in a valid Project Epoch folder")
                else:
                    self.client_status_label.setText("Client: Not Set")
                    self.client_status_label.setStyleSheet("font-size: 9px; color: #999999;")
            # If manual directory exists, keep it and don't change the UI
            return False
    
    def update_manifest_status(self, is_up, check_duration, manifest_data):
        """status logic - don't show misleading 'ONLINE' when no client is set"""
        if self.is_monitoring_disabled:
            return
        
        # Clear starting state when we get first real update
        if self.is_starting:
            self.is_starting = False
        
        self.is_up = is_up
        self.total_checks += 1
        if is_up:
            self.successful_checks += 1
        
        self.last_check_time = datetime.now()
        self.last_manifest_data = manifest_data
        
        # Update status display
        if is_up and manifest_data and 'Version' in manifest_data:
            # Update version display
            self.current_version = manifest_data['Version']
            self.version_label.setText(f"Version: {self.current_version}")
            
            # Different logic based on whether client is set
            if self.client_directory:
                # We have a client directory - do file comparison
                comparison = self.local_detector.compare_with_manifest(self.client_directory, manifest_data)
                self.last_comparison = comparison
                
                status_text, color, tooltip = self.local_detector.get_status_summary(comparison)
                
                # Update client status with comparison result
                client_status_emoji = status_text.split()[0]
                client_status_text = " ".join(status_text.split()[1:])
                
                dir_name = os.path.basename(self.client_directory)
                self.client_status_label.setText(f"{client_status_emoji} {dir_name}")
                self.client_status_label.setStyleSheet(f"font-size: 9px; color: {color}; font-weight: bold;")
                self.client_status_label.setToolTip(f"{tooltip}\nPath: {self.client_directory}")
                
                # Set main status based on comparison
                if comparison["status"] == "up_to_date":
                    status_text = "UP TO DATE"
                    main_color = "#66bb6a"
                elif comparison["status"] == "outdated":
                    status_text = "UPDATE NEEDED"
                    main_color = "#ff9800"
                elif comparison["status"] == "incomplete":
                    status_text = "INCOMPLETE"
                    main_color = "#f44336"
                else:
                    status_text = "COMPARISON ERR"
                    main_color = "#ff9800"
                    
            else:
                # No client directory set - show manifest status only
                status_text = "MANIFEST ONLY"
                main_color = "#64b5f6"
                
                self.client_status_label.setText("Client: Not Set")
                self.client_status_label.setStyleSheet("font-size: 9px; color: #999999;")
                self.client_status_label.setToolTip("Click 'Set Client Dir' to compare with local files")
            
            color = main_color
            
        elif is_up and manifest_data and 'error' in manifest_data:
            error_msg = manifest_data['error']
            
            # Different colors for different error types
            if "timeout" in error_msg.lower():
                status_text = "TIMEOUT"
                color = "#ff9800"
            elif "ssl" in error_msg.lower() or "connection" in error_msg.lower():
                status_text = "CONN ERROR"
                color = "#f44336"
            elif "json" in error_msg.lower() or "format" in error_msg.lower():
                status_text = "FORMAT ERR"
                color = "#ff9800"
            else:
                status_text = "ERROR"
                color = "#f44336"
            
            # Show shortened error
            short_error = error_msg[:25] + "..." if len(error_msg) > 25 else error_msg
            self.version_label.setText(f"Error: {short_error}")
            self.client_status_label.setText("Check Failed")
            self.client_status_label.setStyleSheet("font-size: 9px; color: #f44336;")
            
        else:
            # Complete failure case
            if check_duration > 6:
                status_text = "TIMEOUT"
                color = "#ff9800"
            else:
                status_text = "OFFLINE"
                color = "#f44336"
                
            self.version_label.setText("Version: Connection Failed")
            self.client_status_label.setText("Manifest Offline")
            self.client_status_label.setStyleSheet("font-size: 9px; color: #f44336;")
        
        self.status_text.setText(status_text)
        self.status_text.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {color};")
        self.status_indicator.setStyleSheet(f"color: {color}; font-size: 20px;")
        
        border_color = color
        self.setStyleSheet(f"""
            QWidget {{
                background-color: #404040;
                border: 2px solid {border_color};
                border-radius: 8px;
                margin: 2px;
            }}
        """)
        
        # Update uptime
        if self.total_checks > 0:
            uptime_percent = (self.successful_checks / self.total_checks) * 100
            self.uptime_label.setText(f"Uptime: {uptime_percent:.1f}%")
        
        # Update last check time
        time_str = self.last_check_time.strftime("%H:%M:%S")
        self.last_check_label.setText(f"Last: {time_str}")
    
    def get_comparison_details(self):
        """Get detailed comparison information for logging"""
        if not self.last_comparison:
            return "No comparison data available"
            
        details = []
        for file_detail in self.last_comparison.get("details", []):
            status_emoji = "✅" if file_detail["status"] == "match" else "❌" if file_detail["status"] == "mismatch" else "❓"
            details.append(f"{status_emoji} {file_detail['file']}: {file_detail['message']}")
        
        return "\n".join(details)
    
    def set_to_disabled_state(self):
        """Override to preserve version info when disabled"""
        super().set_to_disabled_state()
        if self.current_version:
            self.version_label.setText(f"Version: {self.current_version}")
        else:
            self.version_label.setText("Version: Unknown")
        self.client_status_label.setText("Monitoring Disabled")
        self.client_status_label.setStyleSheet("font-size: 9px; color: #666666;")
    
    def reset_stats(self):
        """Reset stats but preserve client directory and version info"""
        # Store client directory before calling parent reset
        saved_client_dir = self.client_directory
        saved_version = self.current_version
        
        # Call parent reset for basic stats
        super().reset_stats()
        
        # Restore preserved data
        self.client_directory = saved_client_dir
        self.current_version = saved_version
        
        # Update UI to reflect preserved state
        if self.client_directory:
            dir_name = os.path.basename(self.client_directory)
            self.client_status_label.setText(f"Client: {dir_name}")
            self.client_status_label.setStyleSheet("font-size: 9px; color: #64b5f6; font-weight: bold;")
            self.client_status_label.setToolTip(f"Monitoring: {self.client_directory}")
        else:
            self.client_status_label.setText("Client: Not Set")
            self.client_status_label.setStyleSheet("font-size: 9px; color: #999999;")
            self.client_status_label.setToolTip("Click 'Set Client Dir' to compare with local files")
        
        if self.current_version:
            self.version_label.setText(f"Version: {self.current_version}")
        else:
            self.version_label.setText("Version: Unknown")
        
        # Clear comparison data (this should reset)
        self.last_manifest_data = {}
        self.last_comparison = None

class LocalClientDetector:
    """Detects local Project Epoch client version by comparing files with manifest"""
    
    def __init__(self):
        self.key_files = [
            "Project-Epoch.exe",
            "Data/patch-A.MPQ", 
            "Data/patch-B.MPQ",
            "Data/patch-Y.MPQ",
            "Data/patch-Z.MPQ"
        ]
    
    def detect_client_directory(self, executable_path):
        """Detect client directory from executable path"""
        if not executable_path or not os.path.exists(executable_path):
            return None
            
        client_dir = os.path.dirname(executable_path)
        
        # Verify it looks like a Project Epoch directory
        required_files = ["Project-Epoch.exe", "Data"]
        if all(os.path.exists(os.path.join(client_dir, f)) for f in required_files):
            return client_dir
        return None
    
    def get_file_info(self, client_dir, relative_path):
        """Get file size and MD5 hash for a file"""
        try:
            file_path = os.path.join(client_dir, relative_path.replace('/', os.sep))
            if not os.path.exists(file_path):
                return None
                
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Calculate MD5 hash
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_md5.update(chunk)
            
            return {
                "path": relative_path,
                "size": file_size,
                "hash": hash_md5.hexdigest().lower(),
                "exists": True
            }
        except Exception as e:
            return {
                "path": relative_path,
                "size": 0,
                "hash": "",
                "exists": False,
                "error": str(e)
            }
    
    def compare_with_manifest(self, client_dir, manifest_data):
        """Compare local files with manifest data"""
        if not client_dir or not manifest_data or 'Files' not in manifest_data:
            return {
                "status": "error",
                "message": "Invalid client directory or manifest data"
            }
        
        # Create lookup of manifest files
        manifest_files = {}
        for file_info in manifest_data['Files']:
            path = file_info['Path'].replace('\\', '/')
            manifest_files[path] = {
                "size": file_info['Size'],
                "hash": file_info['Hash'].lower(),
                "path": path
            }
        
        comparison_results = {
            "version": manifest_data.get('Version', 'Unknown'),
            "files_checked": 0,
            "files_matched": 0,
            "files_missing": 0,
            "files_outdated": 0,
            "status": "unknown",
            "details": []
        }
        
        # Check key files that indicate client version
        for file_path in self.key_files:
            normalized_path = file_path.replace('/', '\\')  # Manifest uses backslashes
            
            if normalized_path in manifest_files:
                comparison_results["files_checked"] += 1
                
                # Get local file info
                local_info = self.get_file_info(client_dir, file_path)
                manifest_info = manifest_files[normalized_path]
                
                if not local_info or not local_info["exists"]:
                    comparison_results["files_missing"] += 1
                    comparison_results["details"].append({
                        "file": file_path,
                        "status": "missing",
                        "message": f"File not found locally"
                    })
                    continue
                
                # Compare size and hash
                size_match = local_info["size"] == manifest_info["size"]
                hash_match = local_info["hash"] == manifest_info["hash"]
                
                if size_match and hash_match:
                    comparison_results["files_matched"] += 1
                    comparison_results["details"].append({
                        "file": file_path,
                        "status": "match",
                        "message": "File matches manifest exactly"
                    })
                else:
                    comparison_results["files_outdated"] += 1
                    comparison_results["details"].append({
                        "file": file_path,
                        "status": "mismatch",
                        "message": f"Size: {local_info['size']} vs {manifest_info['size']}, Hash match: {hash_match}",
                        "local_hash": local_info["hash"],
                        "expected_hash": manifest_info["hash"]
                    })
        
        # Determine overall status
        if comparison_results["files_missing"] > 0:
            comparison_results["status"] = "incomplete"
            comparison_results["message"] = f"Missing {comparison_results['files_missing']} critical files"
        elif comparison_results["files_outdated"] > 0:
            comparison_results["status"] = "outdated" 
            comparison_results["message"] = f"Update needed - {comparison_results['files_outdated']} files don't match"
        elif comparison_results["files_matched"] == comparison_results["files_checked"]:
            comparison_results["status"] = "up_to_date"
            comparison_results["message"] = f"All {comparison_results['files_matched']} files match - client is up to date!"
        else:
            comparison_results["status"] = "unknown"
            comparison_results["message"] = "Unable to determine client status"
        
        return comparison_results

    def get_status_summary(self, comparison_result):
        """Get a human-readable status summary"""
        status = comparison_result.get("status", "unknown")
        
        if status == "up_to_date":
            return "✅ Up to Date", "#66bb6a", f"Client matches {comparison_result.get('version', 'current')} perfectly"
        elif status == "outdated":
            return "🆙 Update Available", "#ff9800", f"New version {comparison_result.get('version', '')} available"
        elif status == "incomplete":
            return "❌ Missing Files", "#f44336", "Some game files are missing"
        else:
            return "❓ Unknown Status", "#757575", "Cannot determine client version"

def main():
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("Project Epoch Multi-Server Monitor")
    app.setApplicationVersion("2.0")
    
    monitor = ServerMonitor()
    monitor.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()