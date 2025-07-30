import sys
import math
import time
from collections import deque
from PyQt6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QRadialGradient, QLinearGradient
from PyQt6.QtWidgets import QWidget

# Try to import enhanced graphics libraries
try:
    import pyqtgraph as pg
    import numpy as np
    HAS_ENHANCED_GRAPHICS = True
except ImportError:
    HAS_ENHANCED_GRAPHICS = False

class Particle:
    """Individual particle for effects"""
    def __init__(self, x, y, effect_type="sparkle"):
        self.x = x
        self.y = y
        self.start_x = x
        self.start_y = y
        self.effect_type = effect_type
        self.life = 1.0  # 0.0 to 1.0
        self.max_life = 1.0
        self.size = 3.0
        self.velocity_x = 0
        self.velocity_y = 0
        self.color = QColor(102, 187, 106, 255)  # Green default
        
        # Set properties based on effect type
        if effect_type == "celebration":
            self.velocity_x = (0.5 - __import__('random').random()) * 20
            self.velocity_y = -10 - __import__('random').random() * 15
            self.size = 4.0 + __import__('random').random() * 3
            self.color = QColor(255, 215, 0, 255)  # Gold
        elif effect_type == "sparkle":
            self.velocity_x = (0.5 - __import__('random').random()) * 5
            self.velocity_y = (0.5 - __import__('random').random()) * 5
            self.size = 2.0 + __import__('random').random() * 2
        elif effect_type == "pulse":
            self.size = 8.0
            self.color = QColor(102, 187, 106, 200)
    
    def update(self, dt=0.016):
        """Update particle state"""
        self.life -= dt * 2.0  # 0.5 second lifetime
        
        if self.effect_type == "celebration":
            self.x += self.velocity_x * dt
            self.y += self.velocity_y * dt
            self.velocity_y += 30 * dt  # Gravity
        elif self.effect_type == "sparkle":
            self.x += self.velocity_x * dt
            self.y += self.velocity_y * dt
        elif self.effect_type == "pulse":
            # Pulse grows and fades
            pulse_progress = 1.0 - self.life
            self.size = 8.0 + pulse_progress * 20
            alpha = int(200 * self.life)
            self.color.setAlpha(max(0, alpha))
        
        # Update alpha for fading
        if self.effect_type != "pulse":
            alpha = int(255 * self.life)
            self.color.setAlpha(max(0, alpha))
        
        return self.life > 0

class ParticleSystem:
    """Manages all particle effects"""
    def __init__(self):
        self.particles = []
        self.last_update = time.time()
    
    def add_celebration_burst(self, x, y, count=8):
        """Add celebration particles at position"""
        for _ in range(count):
            self.particles.append(Particle(x, y, "celebration"))
    
    def add_sparkles(self, x, y, count=3):
        """Add sparkle particles at position"""
        for _ in range(count):
            self.particles.append(Particle(x, y, "sparkle"))
    
    def add_pulse(self, x, y):
        """Add pulse effect at position"""
        self.particles.append(Particle(x, y, "pulse"))
    
    def update(self):
        """Update all particles and remove dead ones"""
        current_time = time.time()
        dt = current_time - self.last_update
        self.last_update = current_time
        
        self.particles = [p for p in self.particles if p.update(dt)]
    
    def draw(self, painter, plot_widget):
        """Draw all particles on the plot"""
        if not hasattr(plot_widget, 'getViewBox'):
            return
            
        view_box = plot_widget.getViewBox()
        if view_box is None:
            return
            
        for particle in self.particles:
            # Convert data coordinates to pixel coordinates
            try:
                pixel_pos = view_box.mapViewToDevice(pg.Point(particle.x, particle.y))
                if pixel_pos is not None:
                    painter.setPen(QPen(particle.color, 1))
                    painter.setBrush(QBrush(particle.color))
                    
                    # Draw particle based on type
                    if particle.effect_type == "pulse":
                        # Draw pulsing circle
                        painter.drawEllipse(
                            int(pixel_pos.x() - particle.size/2),
                            int(pixel_pos.y() - particle.size/2),
                            int(particle.size),
                            int(particle.size)
                        )
                    else:
                        # Draw small sparkle/celebration particle
                        painter.drawEllipse(
                            int(pixel_pos.x() - particle.size/2),
                            int(pixel_pos.y() - particle.size/2),
                            int(particle.size),
                            int(particle.size)
                        )
            except:
                continue  # Skip if coordinate conversion fails

class EnhancedGraphWidget(pg.PlotWidget if HAS_ENHANCED_GRAPHICS else QWidget):
    """Enhanced graph widget with visual effects"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        if not HAS_ENHANCED_GRAPHICS:
            # Fallback to simple widget if pyqtgraph not available
            self.setMinimumHeight(150)
            self.setMaximumHeight(200)
            self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #555555;")
            return
        
        # Initialize pyqtgraph plot
        self.setBackground('#1e1e1e')
        self.setLabel('left', 'Uptime %', color='white', size='10pt')
        self.setLabel('bottom', 'Time', color='white', size='10pt')
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setMinimumHeight(150)
        self.setMaximumHeight(200)
        
        # Enhanced features
        self.particle_system = ParticleSystem()
        self.uptime_line = None
        self.gradient_fill = None
        self.last_status = None
        self.current_glow_intensity = 0.3
        self.target_glow_intensity = 0.3
        
        # Animation timer for particles and effects
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_effects)
        self.animation_timer.start(16)  # ~60 FPS
        
        # Data storage
        self.uptime_history = []
        self.time_points = []
        
        # Setup initial plot elements
        self.setup_plot_elements()
    
    def setup_plot_elements(self):
        """Initialize plot elements with enhanced styling"""
        if not HAS_ENHANCED_GRAPHICS:
            return
            
        # Create the main uptime line with glow effect
        glow_pen = pg.mkPen(color='#66bb6a', width=4, style=pg.QtCore.Qt.PenStyle.SolidLine)
        glow_pen.setCapStyle(pg.QtCore.Qt.PenCapStyle.RoundCap)
        glow_pen.setJoinStyle(pg.QtCore.Qt.PenJoinStyle.RoundJoin)
        
        self.uptime_line = self.plot([], [], pen=glow_pen, name='Uptime')
        
        # Create gradient fill area
        self.gradient_fill = pg.FillBetweenItem(
            self.uptime_line, 
            pg.PlotCurveItem([], []),  # Zero line
            brush=pg.mkBrush(color=(102, 187, 106, 50))  # Semi-transparent green
        )
        self.addItem(self.gradient_fill)
    
    def update_with_effects(self, uptime_data, status_changed=False, is_up=False):
        """Update graph with enhanced visual effects"""
        if not HAS_ENHANCED_GRAPHICS:
            # Fallback: just update the widget background color
            color = "#1a4a1a" if is_up else "#1e1e1e"
            self.setStyleSheet(f"background-color: {color}; border: 1px solid #555555;")
            return
        
        if not uptime_data:
            return
            
        # Update data
        self.uptime_history = list(uptime_data)
        self.time_points = list(range(len(uptime_data)))
        
        # Update line glow based on current status
        if is_up:
            self.target_glow_intensity = 1.0
            line_color = '#66bb6a'  # Bright green
            fill_color = (102, 187, 106, 80)  # Brighter green fill
        else:
            self.target_glow_intensity = 0.3
            line_color = '#424242'  # Dim gray
            fill_color = (66, 66, 66, 30)  # Dim gray fill
        
        # Smooth glow transition
        self.current_glow_intensity += (self.target_glow_intensity - self.current_glow_intensity) * 0.1
        
        # Update line with dynamic glow
        glow_width = 2 + self.current_glow_intensity * 3
        glow_pen = pg.mkPen(color=line_color, width=glow_width)
        glow_pen.setCapStyle(pg.QtCore.Qt.PenCapStyle.RoundCap)
        
        # Update plot data
        self.uptime_line.setData(self.time_points, self.uptime_history, pen=glow_pen)
        
        # Update gradient fill
        zero_line = [0] * len(self.uptime_history)
        self.gradient_fill.setCurves(
            pg.PlotCurveItem(self.time_points, self.uptime_history),
            pg.PlotCurveItem(self.time_points, zero_line)
        )
        self.gradient_fill.setBrush(pg.mkBrush(color=fill_color))
        
        # Handle status change effects
        if status_changed and len(self.time_points) > 0:
            current_x = self.time_points[-1]
            current_y = self.uptime_history[-1]
            
            if is_up:
                # Server came UP - celebration!
                self.particle_system.add_celebration_burst(current_x, current_y, count=12)
                self.particle_system.add_pulse(current_x, current_y)
            # No particles when going down - we don't want constant distractions
        
        # Add subtle sparkles on UP segments
        if is_up and len(self.time_points) > 1:
            # Only add sparkles occasionally to avoid overload
            import random
            if random.random() < 0.3:  # 30% chance per update
                current_x = self.time_points[-1]
                current_y = self.uptime_history[-1]
                self.particle_system.add_sparkles(current_x, current_y, count=2)
        
        self.last_status = is_up
    
    def update_effects(self):
        """Update particle effects and animations"""
        if not HAS_ENHANCED_GRAPHICS:
            return
            
        # Update particle system
        self.particle_system.update()
        
        # Trigger repaint if we have active particles
        if self.particle_system.particles:
            self.update()
    
    def paintEvent(self, event):
        """Custom paint event to draw particles"""
        if not HAS_ENHANCED_GRAPHICS:
            super().paintEvent(event)
            return
            
        # Call parent paint event first
        super().paintEvent(event)
        
        # Draw particles on top
        if self.particle_system.particles:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.particle_system.draw(painter, self)
            painter.end()
    
    def clear_graph(self):
        """Clear the graph data and effects"""
        if not HAS_ENHANCED_GRAPHICS:
            return
            
        self.uptime_history.clear()
        self.time_points.clear()
        self.particle_system.particles.clear()
        
        if self.uptime_line:
            self.uptime_line.setData([], [])

# Factory function to create appropriate graph widget
def create_graph_widget(parent=None, enhanced=True):
    """Factory function to create graph widget based on availability"""
    if enhanced and HAS_ENHANCED_GRAPHICS:
        return EnhancedGraphWidget(parent)
    elif HAS_ENHANCED_GRAPHICS:
        # Standard pyqtgraph widget
        widget = pg.PlotWidget(parent)
        widget.setBackground('#1e1e1e')
        widget.setLabel('left', 'Uptime %', color='white', size='10pt')
        widget.setLabel('bottom', 'Time', color='white', size='10pt')
        widget.showGrid(x=True, y=True, alpha=0.3)
        widget.setMinimumHeight(150)
        widget.setMaximumHeight(200)
        return widget
    else:
        # Fallback to simple colored widget
        widget = QWidget(parent)
        widget.setMinimumHeight(150)
        widget.setMaximumHeight(200)
        widget.setStyleSheet("background-color: #1e1e1e; border: 1px solid #555555;")
        return widget