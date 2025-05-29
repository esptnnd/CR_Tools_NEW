from PyQt5.QtWidgets import QTextEdit, QMainWindow, QPushButton, QLineEdit, QProgressBar, QLabel, QMenuBar, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QLinearGradient, QPen, QPalette, QBrush, QPixmap, QIcon, QFont
import os

# Style configuration
STYLE_CONFIG = {
    'colors': {
        'primary': '#00FF00',  # Green
        'secondary': '#1E90FF',  # Dodger Blue
        'background': '#1A1A1A',  # Dark Gray
        'text': '#E0E0E0',  # Light Gray
        'border': 'rgba(0, 255, 0, 0.3)',
        'progress': '#00FF00',
        'menu_bg': '#000000',  # Black
    },
    'opacity': {
        'terminal': 0.4,
        'button': 0.9,
        'input': 0.8,
    },
    'fonts': {
        'default': ('Consolas', 10, 'bold'),
        'title': ('Arial', 12, 'bold'),
        'button': ('Arial', 10, 'bold'),
    },
    'sizes': {
        'logo_width': 0.09,  # 9% of window width
        'padding': 10,
    }
}

class TransparentTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(26, 26, 26, 0.2);
                color: {STYLE_CONFIG['colors']['primary']};
                border: 1px solid {STYLE_CONFIG['colors']['border']};
                font-family: {STYLE_CONFIG['fonts']['default'][0]};
                font-size: {STYLE_CONFIG['fonts']['default'][1]}pt;
                font-weight: bold;
            }}
        """)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.viewport().rect()
        
        # Draw base semi-transparent background with blur effect
        painter.fillRect(rect, QColor(26, 26, 26, int(255 * 0.15)))
        
        # Draw gradient overlay for glass effect
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0, QColor(26, 26, 26, 20))
        gradient.setColorAt(0.5, QColor(26, 26, 26, 30))
        gradient.setColorAt(1, QColor(26, 26, 26, 20))
        painter.fillRect(rect, gradient)
        
        # Draw subtle highlight at the top
        highlight = QLinearGradient(0, 0, 0, 2)
        highlight.setColorAt(0, QColor(255, 255, 255, 10))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillRect(rect.adjusted(0, 0, 0, -rect.height() + 2), highlight)
        
        # Draw border effects
        painter.setPen(QPen(QColor(STYLE_CONFIG['colors']['primary']), 1))
        painter.drawRect(rect.adjusted(1, 1, -1, -1))
        
        # Draw subtle inner glow
        glow = QPen(QColor(STYLE_CONFIG['colors']['primary']), 1, Qt.DotLine)
        glow.setColor(QColor(STYLE_CONFIG['colors']['primary']))
        painter.setPen(glow)
        painter.drawRect(rect.adjusted(2, 2, -2, -2))
        
        super().paintEvent(event)

class StyledPushButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(26, 26, 26, 0.4);
                color: {STYLE_CONFIG['colors']['primary']};
                border: 1px solid {STYLE_CONFIG['colors']['border']};
                border-radius: 4px;
                padding: 5px;
                font-family: {STYLE_CONFIG['fonts']['button'][0]};
                font-size: {STYLE_CONFIG['fonts']['button'][1]}pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 255, 0, 0.15);
                border: 1px solid {STYLE_CONFIG['colors']['primary']};
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 255, 0, 0.25);
            }}
        """)

class StyledLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(26, 26, 26, 0.3);
                color: {STYLE_CONFIG['colors']['primary']};
                border: 1px solid {STYLE_CONFIG['colors']['border']};
                border-radius: 4px;
                padding: 5px;
                font-family: {STYLE_CONFIG['fonts']['default'][0]};
                font-size: {STYLE_CONFIG['fonts']['default'][1]}pt;
                font-weight: bold;
            }}
            QLineEdit:focus {{
                border: 1px solid {STYLE_CONFIG['colors']['primary']};
                background-color: rgba(26, 26, 26, 0.4);
            }}
        """)

class StyledProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Basic setup
        self.setFormat("%p%")
        self.setTextVisible(True)
        self.setAlignment(Qt.AlignCenter)
        
        # Create label for text beside progress bar
        self.label = QLabel(self)
        self.label.setStyleSheet("""
            QLabel {
                color: white;
                font-family: Consolas;
                font-size: 10pt;
                font-weight: bold;
                background: transparent;
            }
        """)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # Set white text color
        self.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(0, 255, 0, 0.3);
                border-radius: 4px;
                background-color: rgba(26, 26, 26, 0.3);
            }
            QProgressBar::chunk {
                background-color: #00FF00;
                border-radius: 3px;
            }
        """)
        
    def setText(self, text):
        """Set the text that appears beside the progress bar"""
        self.label.setText(text)
        
    def resizeEvent(self, event):
        """Handle resize events to position the label"""
        super().resizeEvent(event)
        # Position label to the right of the progress bar
        self.label.setGeometry(self.width() + 10, 0, 200, self.height())
        
    def setValue(self, value):
        """Override setValue to update both progress and label"""
        super().setValue(value)
        # Update label text if needed
        if hasattr(self, 'label'):
            self.label.setText(f"{value}%")

class StyledLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            QLabel {{
                color: {STYLE_CONFIG['colors']['primary']};
                font-family: {STYLE_CONFIG['fonts']['default'][0]};
                font-size: {STYLE_CONFIG['fonts']['default'][1]}pt;
                font-weight: bold;
            }}
        """)

class StyledMenuBar(QMenuBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QMenuBar {{
                background-color: rgba(0, 0, 0, 0.7);
                color: white;
                font-family: {STYLE_CONFIG['fonts']['default'][0]};
                font-size: {STYLE_CONFIG['fonts']['default'][1]}pt;
                font-weight: bold;
            }}
            QMenuBar::item {{
                background-color: transparent;
                color: white;
                padding: 5px 10px;
                font-weight: bold;
            }}
            QMenuBar::item:selected {{
                background-color: rgba(255, 255, 255, 0.2);
            }}
            QMenu {{
                background-color: rgba(0, 0, 0, 0.8);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            QMenu::item {{
                padding: 5px 20px;
                font-weight: bold;
            }}
            QMenu::item:selected {{
                background-color: rgba(255, 255, 255, 0.2);
            }}
        """)

class CustomTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        
        # Create layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Create tab bar
        self.tab_bar = QWidget()
        self.tab_bar.setAttribute(Qt.WA_TranslucentBackground)
        self.tab_bar.setFixedHeight(40)
        self.tab_bar_layout = QHBoxLayout(self.tab_bar)
        self.tab_bar_layout.setContentsMargins(5, 5, 5, 0)
        self.tab_bar_layout.setSpacing(2)
        
        # Create content area
        self.content_area = QWidget()
        self.content_area.setAttribute(Qt.WA_TranslucentBackground)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add widgets to main layout
        self.layout.addWidget(self.tab_bar)
        self.layout.addWidget(self.content_area)
        
        # Initialize tab data
        self.tabs = []
        self.current_tab = None
        
        # Set styles
        self.setStyleSheet("""
            QWidget {
                background: transparent;
            }
        """)
        
    def addTab(self, widget, label):
        # Create tab button
        tab_button = QPushButton(label)
        tab_button.setCheckable(True)
        tab_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 0.5);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: rgba(0, 0, 0, 0.7);
                border-bottom: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.6);
            }
        """)
        
        # Add to tab bar
        self.tab_bar_layout.addWidget(tab_button)
        
        # Hide the widget initially
        widget.setAttribute(Qt.WA_TranslucentBackground)
        widget.hide()
        self.content_layout.addWidget(widget)
        
        # Store tab data
        self.tabs.append({
            'button': tab_button,
            'widget': widget
        })
        
        # Connect button
        tab_button.clicked.connect(lambda: self.switchTab(len(self.tabs) - 1))
        
        # If this is the first tab, select it
        if len(self.tabs) == 1:
            self.switchTab(0)
            
    def switchTab(self, index):
        # Uncheck all buttons
        for tab in self.tabs:
            tab['button'].setChecked(False)
            tab['widget'].hide()
            
        # Show selected tab
        self.tabs[index]['button'].setChecked(True)
        self.tabs[index]['widget'].show()
        self.current_tab = index
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw semi-transparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 128))  # 50% opacity black
        
        # Draw border
        painter.setPen(QPen(QColor(255, 255, 255, 51)))  # 20% opacity white
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        
        super().paintEvent(event)

def setup_window_style(window):
    """Setup window styling including background and logo"""
    # Set window icon
    logo_path = os.path.join(os.path.dirname(__file__), 'image', 'ericsson_logo.png')
    if os.path.exists(logo_path):
        window.setWindowIcon(QIcon(logo_path))

    # Set background image
    background_path = os.path.join(os.path.dirname(__file__), 'image', 'ericsson.png')
    logo_white_path = os.path.join(os.path.dirname(__file__), 'image', 'ericsson_logo_white.png')
    if os.path.exists(background_path) and os.path.exists(logo_white_path):
        # Create background
        palette = QPalette()
        # Load and scale background image
        bg_pixmap = QPixmap(background_path)
        new_height = int(bg_pixmap.height() * (window.width() / bg_pixmap.width()))
        scaled_bg = bg_pixmap.scaled(window.width(), new_height, 
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        # Load and scale small logo
        logo_pixmap = QPixmap(logo_white_path)
        logo_width = int(window.width() * STYLE_CONFIG['sizes']['logo_width'])
        logo_height = int(logo_pixmap.height() * (logo_width / logo_pixmap.width()))
        small_logo = logo_pixmap.scaled(logo_width, logo_height, 
                                      Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        # Create background
        background = QPixmap(window.size())
        # Create a painter to draw both images
        painter = QPainter(background)
        # Draw background image
        painter.drawPixmap(0, 0, scaled_bg)
        # Draw the small logo at top right
        x_pos = window.width() - logo_width - STYLE_CONFIG['sizes']['padding']
        y_pos = STYLE_CONFIG['sizes']['padding']
        painter.drawPixmap(x_pos, y_pos, small_logo)
        painter.end()
        
        palette.setBrush(QPalette.Window, QBrush(background))
        window.setPalette(palette)
        window.setAutoFillBackground(True)

    # Set menu bar style
    if hasattr(window, 'menuBar'):
        window.setMenuBar(StyledMenuBar(window))

def update_window_style(window):
    """Update window styling when resized"""
    background_path = os.path.join(os.path.dirname(__file__), 'image', 'ericsson.png')
    logo_white_path = os.path.join(os.path.dirname(__file__), 'image', 'ericsson_logo_white.png')
    
    if os.path.exists(background_path) and os.path.exists(logo_white_path):
        palette = QPalette()
        # Load and scale background image
        bg_pixmap = QPixmap(background_path)
        new_height = int(bg_pixmap.height() * (window.width() / bg_pixmap.width()))
        scaled_bg = bg_pixmap.scaled(window.width(), new_height, 
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        # Load and scale small logo
        logo_pixmap = QPixmap(logo_white_path)
        logo_width = int(window.width() * STYLE_CONFIG['sizes']['logo_width'])
        logo_height = int(logo_pixmap.height() * (logo_width / logo_pixmap.width()))
        small_logo = logo_pixmap.scaled(logo_width, logo_height, 
                                      Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        # Create background
        background = QPixmap(window.size())
        # Create a painter to draw both images
        painter = QPainter(background)
        # Draw background image
        painter.drawPixmap(0, 0, scaled_bg)
        # Draw the small logo at top right
        x_pos = window.width() - logo_width - STYLE_CONFIG['sizes']['padding']
        y_pos = STYLE_CONFIG['sizes']['padding']
        painter.drawPixmap(x_pos, y_pos, small_logo)
        painter.end()
        
        palette.setBrush(QPalette.Window, QBrush(background))
        window.setPalette(palette) 