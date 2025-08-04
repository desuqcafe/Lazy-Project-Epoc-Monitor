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
            "sound_notifications_enabled": True,
            "settings_location": "auto",  # auto, portable, appdata, custom
            "custom_settings_path": "",
            "auto_save_settings": True,
            "keep_settings_cache": True
        }
        self.settings = self.defaults.copy()
        self.current_settings_path = None
        self._initialize_settings_location()

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
            "Gurubashi": {"host": "game.project-epoch.net", "port": 8086, "type": "PvP Realm"}
        }
        
        # Initialize settings
        self.user_settings = UserSettings()
        settings = self.user_settings.load()
        
        # Apply loaded settings
        self.sound_notifications_enabled = settings.get("sound_notifications_enabled", True)
        self.auto_action_mode = settings["auto_action_mode"]
        self.client_executable_path = settings["client_executable_path"]
        self.selected_sound = settings["selected_sound"]
        self.sound_volume = settings["sound_volume"]
        self.is_simulating = False
        
        # Audio resources path
        self.audio_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "audio")
        self.available_sounds = self.scan_audio_files()
        
        # Validate selected sound still exists
        if self.selected_sound not in self.available_sounds:
            self.selected_sound = "gotime.mp3" if "gotime.mp3" in self.available_sounds else "System Default"
        
        # Monitoring threads and server cards
        self.monitor_threads = {}
        self.server_cards = {}
        self.start_time = None
        self.max_log_lines = 25
        
        self.threads_to_cleanup = []
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._cleanup_finished_threads)
        self.cleanup_timer.start(1000)  # Check every second for finished threads
        
        self.init_ui()
        self.load_ui_settings()
        self.update_client_button_states()

    def _cleanup_finished_threads(self):
        if not self.threads_to_cleanup:
            return
        
        cleaned_up = []
        for thread in self.threads_to_cleanup[:]:  # Create copy to avoid modification during iteration
            try:
                if thread.isFinished():
                    cleaned_up.append(thread)
                    thread.deleteLater()
                elif not thread.running:
                    # Thread was signaled to stop but hasn't finished yet
                    # Check if it's been too long (stuck thread)
                    if not hasattr(thread, '_stop_time'):
                        thread._stop_time = time.time()
                    elif time.time() - thread._stop_time > 10:  # 10 second timeout
                        self.add_to_log(f"Force terminating stuck thread for {getattr(thread, 'server_name', 'unknown')}")
                        thread.terminate()
                        cleaned_up.append(thread)
            except Exception as e:
                # If we can't check the thread state, assume it's dead
                cleaned_up.append(thread)
        
        for thread in cleaned_up:
            if thread in self.threads_to_cleanup:
                self.threads_to_cleanup.remove(thread)
    
    def load_ui_settings(self):
        settings = self.user_settings.settings
        
        interval = max(2, min(300, settings.get("check_interval", 5)))
        self.delay_spinbox.setValue(interval)
        
        self.sound_notifications_cb.setChecked(self.sound_notifications_enabled)
        
        volume = max(0, min(100, settings.get("sound_volume", 35)))
        self.sound_volume = volume
        self.volume_slider.setValue(volume)
        self.volume_label.setText(f"{volume}%")
        
        if self.selected_sound in self.available_sounds:
            self.sound_combo.setCurrentText(self.selected_sound)
        
        self.update_auto_action_checkboxes()
        
        
        if self.client_executable_path and os.path.exists(self.client_executable_path):
            filename = os.path.basename(self.client_executable_path)
            self.client_path_label.setText(f"Client: {filename}")
            self.client_path_label.setStyleSheet("color: #66bb6a; font-weight: bold; font-size: 11px;")
        
        self.server_cards["Auth"].enabled_cb.setChecked(settings.get("monitor_auth", True))
        self.server_cards["Kezan"].enabled_cb.setChecked(settings.get("monitor_kezan", True))
        self.server_cards["Gurubashi"].enabled_cb.setChecked(settings.get("monitor_gurubashi", True))
        
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
            "monitor_gurubashi": self.server_cards["Gurubashi"].enabled_cb.isChecked()
        }
        self.user_settings.update_multiple(current_settings)
        self.user_settings.update_multiple(current_settings)
    
    def closeEvent(self, event):
        self.save_current_settings()
        self.stop_all_monitoring()
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
            card = ServerCard(server_name, config["type"], config["port"])
            card.monitoring_toggled.connect(self.on_server_monitoring_toggled)
            self.server_cards[server_name] = card
            cards_layout.addWidget(card, row, col)
            
            col += 1
            if col > 2:
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
                self.stop_single_server_monitoring_async(server_name)
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
        
    def stop_single_server_monitoring_async(self, server_name):
        if server_name not in self.monitor_threads:
            return False
        
        try:
            thread = self.monitor_threads[server_name]
            if thread.running:
                thread.stop()
                self.threads_to_cleanup.append(thread)
                self.add_to_log(f"Signaled {server_name} monitoring to stop")
            
            # Remove from active threads immediately
            del self.monitor_threads[server_name]
            return True
            
        except Exception as e:
            self.add_to_log(f"Error stopping monitoring for {server_name}: {e}")
            return False

    def stop_single_server_monitoring(self, server_name):
        if server_name not in self.monitor_threads:
            return False
        
        try:
            thread = self.monitor_threads[server_name]
            if thread.running:
                thread.stop()
                # Only use blocking wait during shutdown
                if hasattr(self, '_shutting_down') and self._shutting_down:
                    thread.wait(2000)  # Max 2 second wait during shutdown
                else:
                    # During normal operation, use async cleanup
                    self.threads_to_cleanup.append(thread)
            
            # Remove from active threads
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
            if card.enabled_cb.isChecked():
                # Show starting state immediately
                card.set_to_starting_state()  # NEW!
                enabled_servers.append(server_name)
                self.start_single_server_monitoring(server_name)
        
        if enabled_servers:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.ui_timer.start(1000)
            
            servers_list = ", ".join(enabled_servers)
            self.add_to_log(f"Starting monitoring: {servers_list}...")
        else:
            self.add_to_log("No servers enabled for monitoring!")

    def test_connection_detection(self):
        self.add_to_log("Auto-detecting server connections...")
        detected = self.detect_active_server_connections()
        if detected:
            for server, ip in detected.items():
                self.add_to_log(f"✓ Detected {server} active on {ip}")
        else:
            self.add_to_log("No active realm connections found")
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
        for card in self.server_cards.values():
            card.reset_stats()
        
        self.add_to_log("Cleared all server statistics")
    

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
        
        # Only notify if Auth is online (makes sense - can't play without auth)
        if not self.is_auth_server_online():
            return False
                
        return True
    
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
        if server_name in self.server_cards:
            old_status = self.server_cards[server_name].is_up
            self.server_cards[server_name].update_status(is_up, check_duration)
            
            status_changed = old_status != is_up
            
            current_time = datetime.now().strftime("%H:%M:%S")
            status_text = "ONLINE" if is_up else ("TIMEOUT" if check_duration > 1.8 else "OFFLINE")
            
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
            
            log_entry = f"[{current_time}] {server_name}: {status_text}{quality_indicator}"
            if status_changed:
                log_entry += " ⚡"
            
            self.add_to_log(log_entry)
            
            if self.should_send_notification(server_name, is_up, status_changed):
                if is_up and check_duration > 2.0:
                    self.add_to_log(f"⚠️ {server_name} online but very slow response - likely rejecting connections")
                elif not is_up and status_text == "REJECTING":
                    self.add_to_log(f"🚫 {server_name} appears to be rejecting game connections")
                
                threading.Thread(target=self.play_sound, daemon=True).start()
                
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
                if not self.is_auth_server_online():
                    self.add_to_log(f"⚠️ {server_name} status changed but Auth offline - no alert")
                elif status_text == "REJECTING":
                    self.add_to_log(f"🚫 {server_name} is rejecting connections - no alert sent")
                elif not self.sound_notifications_enabled:
                    self.add_to_log(f"🔇 {server_name} status changed but notifications disabled")
            
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
            self.user_settings.set("client_executable_path", file_path)
    
    def launch_client(self):
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
                        
                        # Exclude Discord and other apps with strict filtering
                        excluded_keywords = ["Monitor", "Chrome", "Firefox", "Edge", "Browser", "Discord", 
                                           "Visual Studio", "Notepad", "Calculator", "Task Manager",
                                           "File Explorer", "Windows Security", "Settings"]
                        
                        if any(keyword.lower() in window_title.lower() for keyword in excluded_keywords):
                            return True
                        
                        # Look for game windows with priority order
                        target_keywords = []
                        
                        # Add executable name if selected (highest priority)
                        if self.client_executable_path:
                            exe_name = os.path.splitext(os.path.basename(self.client_executable_path))[0]
                            target_keywords.append(exe_name)
                        
                        # Add Project Epoch specific keywords
                        target_keywords.extend([
                            "Project Epoch",
                            "World of Warcraft", 
                            "WoW"
                        ])
                        
                        # Check if window title matches any target keywords
                        for keyword in target_keywords:
                            if keyword.lower() in window_title.lower():
                                # Additional validation for Project Epoch to avoid Discord/browser tabs
                                if "project epoch" in window_title.lower():
                                    excluded_in_title = ["discord", "chrome", "firefox", "edge", "browser", "tab"]
                                    if any(excluded.lower() in window_title.lower() for excluded in excluded_in_title):
                                        continue  # Skip this window, it's a browser/discord tab
                                
                                try:
                                    # Bring window to front with multiple methods for reliability
                                    user32.SetForegroundWindow(hwnd)
                                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                                    user32.SetActiveWindow(hwnd)
                                    user32.BringWindowToTop(hwnd)
                                    
                                    found_window = True
                                    self.add_to_log(f"Focused window: {window_title}")
                                    return False  # Stop enumeration
                                except Exception as e:
                                    self.add_to_log(f"Failed to focus '{window_title}': {e}")
                                    continue
                
                return True  # Continue enumeration
            
            # Enumerate all windows
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
            
            if not found_window:
                self.add_to_log("No Project Epoch/WoW windows found to focus")
            
            return found_window
            
        except Exception as e:
            self.add_to_log(f"Error bringing client to front: {e}")
            return False
    
    def test_focus_client(self):
        self.add_to_log("Testing window focus...")
        success = self.bring_client_to_front()
        if not success:
            self.add_to_log("Tip: Make sure Project Epoch is running first!")
    
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
        """Play notification sound with volume control (updated logic)"""
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