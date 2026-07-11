import sys
import os
import json
import struct
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QDockWidget, QLineEdit, QDialog, QPlainTextEdit,
                             QLabel, QFileDialog, QMessageBox, QGraphicsView,
                             QGraphicsScene, QGraphicsPathItem,
                             QGraphicsRectItem, QGraphicsTextItem, QFormLayout,
                             QPushButton, QGridLayout, QMenu, QInputDialog,
                             QSlider, QDoubleSpinBox, QHBoxLayout, QWidgetAction,
                             QCheckBox, QScrollArea, QComboBox)
from PyQt6.QtGui import (QAction, QColor, QFont, QShortcut, QKeySequence, QPixmap,
                         QPainterPath, QPen, QBrush, QColor, QPainter,
                         QPainterPathStroker)
from PyQt6.QtCore import Qt, QSettings, QTimer, QPointF, QRectF, QProcess
from PyQt6.Qsci import QsciScintilla, QsciLexerPython, QsciAPIs
from lexer import OscarLexer
from PyQt6.QtNetwork import QTcpSocket, QTcpServer, QHostAddress, QUdpSocket
from PyQt6.QtCore import QRunnable, QObject, QThreadPool, pyqtSignal
from PyQt6.QtGui import QImage
import collections
import itertools

class ScintillaEditor(QsciScintilla):
    """A fully-featured code editor widget using QScintilla."""

    def __init__(self):
        super().__init__()

        # Base Font setup
        editor_font = QFont("Consolas", 12)
        self.setFont(editor_font)
        self.setMarginsFont(editor_font)
        # Syntax Highlighting (The Lexer)
        self.lexer = OscarLexer(self)
        self.setLexer(self.lexer)
        self.setup_autocompletion()

        # Line Numbers (Margins)
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "0000")  # Reserves width for up to 9999 lines
        self.setMarginsBackgroundColor(QColor("#2b2b2b"))
        self.setMarginsForegroundColor(QColor("#888888"))

        # Auto-Indentation and Tabs
        self.setAutoIndent(True)
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setIndentationGuides(True)

        # Caret (Cursor) styling
        self.setCaretForegroundColor(QColor("white"))
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#2a2d2e"))  # Highlights current line

        # Bracket Matching
        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)

        self.setScrollWidthTracking(True)
        self.setScrollWidth(1)

        self.FLASH_INDICATOR = 8  # Indicators 0-7 are reserved for lexers
        self.SendScintilla(QsciScintilla.SCI_INDICSETSTYLE, self.FLASH_INDICATOR, QsciScintilla.INDIC_STRAIGHTBOX)
        self.SendScintilla(QsciScintilla.SCI_INDICSETFORE, self.FLASH_INDICATOR, QColor("#ffffff"))
        self.SendScintilla(QsciScintilla.SCI_INDICSETUNDER, self.FLASH_INDICATOR, True)  # Draw beneath text
        
        self.SYNTH_INDICATORS_START = 9

        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self._fade_flash)
        self.flash_alpha = 0
        self.flash_start_pos = 0
        self.flash_length = 0
        
        self.current_synth_colors = {}
        self.textChanged.connect(self._on_text_changed)

    def flash_lines(self, start_line, end_line):
        """Highlights a block of lines and begins the fade animation."""
        # Clear any existing flash if the user is mashing Ctrl+Enter
        if self.flash_length > 0:
            self.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, self.FLASH_INDICATOR)
            self.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, 0, self.length())

        # Calculate character positions
        self.flash_start_pos = self.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, start_line)
        end_pos = self.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, end_line + 1)

        # Fallback if end_line is the very last line of the document
        if end_pos == -1:
            end_pos = self.SendScintilla(QsciScintilla.SCI_GETTEXTLENGTH)

        self.flash_length = end_pos - self.flash_start_pos

        # Reset alpha and paint the highlight
        self.flash_alpha = 100  # Max opacity (out of 255)
        self.SendScintilla(QsciScintilla.SCI_INDICSETALPHA, self.FLASH_INDICATOR, self.flash_alpha)
        self.SendScintilla(QsciScintilla.SCI_INDICSETOUTLINEALPHA, self.FLASH_INDICATOR, self.flash_alpha)

        self.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, self.FLASH_INDICATOR)
        self.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE, self.flash_start_pos, self.flash_length)

        # Start animation at ~30 FPS
        self.flash_timer.start(30)

    def _fade_flash(self):
        """Animation tick that reduces opacity until invisible."""
        self.flash_alpha -= 10
        if self.flash_alpha <= 0:
            self.flash_timer.stop()
            self.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, self.FLASH_INDICATOR)
            self.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, self.flash_start_pos, self.flash_length)
            self.flash_length = 0
        else:
            self.SendScintilla(QsciScintilla.SCI_INDICSETALPHA, self.FLASH_INDICATOR, self.flash_alpha)
            self.SendScintilla(QsciScintilla.SCI_INDICSETOUTLINEALPHA, self.FLASH_INDICATOR, self.flash_alpha)

    def _on_text_changed(self):
        if self.current_synth_colors:
            self.update_synth_highlights(self.current_synth_colors)
            
    def update_synth_highlights(self, synth_colors):
        self.current_synth_colors = synth_colors
        import re
        
        # Clear all previous synth indicators
        for i in range(self.SYNTH_INDICATORS_START, self.SYNTH_INDICATORS_START + 16):
            self.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, i)
            self.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, 0, self.length())
            
        if not synth_colors:
            return
            
        indic_idx = self.SYNTH_INDICATORS_START
        text = self.text()
        
        for synth_name, color in synth_colors.items():
            if indic_idx > self.SYNTH_INDICATORS_START + 15:
                break
                
            self.SendScintilla(QsciScintilla.SCI_INDICSETSTYLE, indic_idx, QsciScintilla.INDIC_SQUIGGLE)
            self.SendScintilla(QsciScintilla.SCI_INDICSETFORE, indic_idx, color)
            self.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, indic_idx)
            
            for match in re.finditer(rf'\b{re.escape(synth_name)}\b', text):
                self.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE, match.start(), match.end() - match.start())
                
            indic_idx += 1

    def _find_oscar_py(self):
        import os
        
        # We need to know where oscar-lc is.
        # Assuming oscar-ide and oscar-lc are siblings:
        ide_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        parent_dir = os.path.dirname(ide_root)
        guess_path = os.path.join(parent_dir, 'oscar-lc', 'src', 'oscar.py')
        if os.path.exists(guess_path):
            return guess_path
            
        return None

    def setup_autocompletion(self):
        self.api = QsciAPIs(self.lexer)
        if hasattr(self.lexer, 'api_data'):
            for kw in self.lexer.api_data.get("python_keywords", []):
                self.api.add(kw)
                
        # Dynamically load OSCAR classes and methods from oscar.py
        oscar_py_path = self._find_oscar_py()
        if oscar_py_path:
            import ast
            try:
                with open(oscar_py_path, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read())
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # Only include relevant classes
                        if node.name in ["Synth", "Patch", "Master", "Scope", "Renderer", "Control", "MidiInput"]:
                            self.api.add(node.name)
                            # Add methods
                            for item in node.body:
                                if isinstance(item, ast.FunctionDef) and not item.name.startswith('_'):
                                    defaults = item.args.defaults
                                    args_list = item.args.args
                                    default_offset = len(args_list) - len(defaults)
                                    args = []
                                    for i, arg in enumerate(args_list):
                                        if arg.arg != 'self':
                                            arg_str = arg.arg
                                            if arg.annotation:
                                                arg_str += f": {ast.unparse(arg.annotation)}"
                                            if i >= default_offset:
                                                default_val = ast.unparse(defaults[i - default_offset])
                                                arg_str += f"={default_val}"
                                            args.append(arg_str)
                                    args_str = ", ".join(args)
                                    doc = ast.get_docstring(item)
                                    if doc:
                                        # First sentence of docstring for brevity in popup
                                        short_doc = doc.strip().split('\n')[0]
                                        self.api.add(f"{item.name}({args_str}) - {short_doc}")
                                    else:
                                        self.api.add(f"{item.name}({args_str})")
            except Exception as e:
                print(f"Failed to parse oscar.py for hinting: {e}")
        else:
            # Fallback to static JSON
            if hasattr(self.lexer, 'api_data'):
                for cls in self.lexer.api_data.get("oscar_classes", []):
                    self.api.add(cls)
                for method in self.lexer.api_data.get("oscar_methods", []):
                    self.api.add(method)
                for const in self.lexer.api_data.get("oscar_constants", []):
                    self.api.add(const)
                    
        self.api.prepare()
        self.setAutoCompletionSource(QsciScintilla.AutoCompletionSource.AcsAll)
        self.setAutoCompletionThreshold(2)
        
        # Setup Call Tips for function hinting
        self.setCallTipsStyle(QsciScintilla.CallTipsStyle.CallTipsNoContext)
        self.setCallTipsVisible(-1)


from PyQt6.QtGui import QPainterPathStroker


class PatchWire(QGraphicsPathItem):
    """Draws a smooth, adaptive Bezier curve between nodes."""

    def __init__(self, start_pos, end_pos, synth_name=None, channel_num=None, is_temp=False):
        super().__init__()
        self.setZValue(-1)  # Keep wires behind nodes

        # Store metadata for deletion later
        self.synth_name = synth_name
        self.channel_num = channel_num

        self.base_color = QColor("#4EC9B0")
        self.pen = QPen(self.base_color)
        self.pen.setWidth(2)

        if is_temp:
            self.pen.setStyle(Qt.PenStyle.DashLine)
            self.pen.setColor(QColor(78, 201, 176, 150))
        else:
            # Enable selection for permanent wires
            self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.setAcceptHoverEvents(True)

        self.setPen(self.pen)
        self.update_positions(start_pos, end_pos)

    def hoverEnterEvent(self, event):
        if not self.isSelected():
            self.pen.setColor(self.base_color.lighter(130))
            self.pen.setWidth(3)
            self.setPen(self.pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self.pen.setColor(self.base_color)
            self.pen.setWidth(2)
            self.setPen(self.pen)
        super().hoverLeaveEvent(event)

    def update_positions(self, start_pos, end_pos):
        """Recalculates the Bezier curve on the fly."""
        path = QPainterPath()
        path.moveTo(start_pos)

        dist = (end_pos.x() - start_pos.x()) / 2
        path.cubicTo(start_pos.x() + dist, start_pos.y(),
                     end_pos.x() - dist, end_pos.y(),
                     end_pos.x(), end_pos.y())
        self.setPath(path)

    def shape(self):
        """Creates a thicker, invisible hit-box so the wire is easy to click."""
        stroker = QPainterPathStroker()
        stroker.setWidth(10)  # 10px click radius
        return stroker.createStroke(self.path())

    def itemChange(self, change, value):
        """Fires automatically when the user clicks the wire."""
        if change == QGraphicsPathItem.GraphicsItemChange.ItemSelectedHasChanged:
            if value:  # Is Selected
                self.pen.setColor(QColor("#ffffff"))
                self.pen.setWidth(4)
            else:  # Deselected
                self.pen.setColor(self.base_color)
                self.pen.setWidth(2)
            self.setPen(self.pen)
        return super().itemChange(change, value)


class PatchNode(QGraphicsRectItem):
    """A dense, list-style node representing a Synth or a Channel."""

    def __init__(self, name, node_type="synth", width=100, height=26, color=None):
        super().__init__(0, 0, width, height)
        self.name = name
        self.node_type = node_type
        self.base_color = color if color else QColor("#333333")

        self.setBrush(QBrush(self.base_color))
        self.setPen(QPen(QColor("#1e1e1e"), 1))

        self.text = QGraphicsTextItem(name, self)
        self.text.setDefaultTextColor(QColor("#dddddd"))
        font = QFont("Consolas", 10)
        self.text.setFont(font)
        
        self.icon_text = QGraphicsTextItem("", self)
        self.icon_text.setDefaultTextColor(QColor("#dddddd"))
        self.icon_text.setFont(font)

        text_rect = self.text.boundingRect()
        if node_type == "synth":
            self.text.setPos(5, (height - text_rect.height()) / 2)
        else:
            self.text.setPos(width - text_rect.width() - 5, (height - text_rect.height()) / 2)

    def get_port_position(self):
        rect = self.sceneBoundingRect()
        if self.node_type == "synth":
            return QPointF(rect.right(), rect.center().y())
        else:
            return QPointF(rect.left(), rect.center().y())

    def set_volume_icon(self, is_muted):
        if self.node_type == "synth":
            icon = "🔇" if is_muted else "🔊"
            self.icon_text.setPlainText(icon)
            
            icon_rect = self.icon_text.boundingRect()
            self.icon_text.setPos(self.rect().width() - icon_rect.width() - 5, (self.rect().height() - icon_rect.height()) / 2)

    def set_highlight(self, active: bool):
        """Visually pops the node when a wire is hovering over it."""
        if active:
            self.setPen(QPen(QColor("#4EC9B0"), 2))
            self.setBrush(QBrush(self.base_color.lighter(130)))
        else:
            self.setPen(QPen(QColor("#1e1e1e"), 1))
            self.setBrush(QBrush(self.base_color))


class PatchBayView(QGraphicsView):
    """The main widget containing the interactive node scene."""

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)  # Allows drag-to-select multiple wires!
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.nodes = {}
        self._synths = []
        self._channels = []
        self._patches = []
        self.node_width = 100
        self.node_height = 26

        # Interaction State
        self.drag_start_node = None
        self.hovered_node = None
        self.temp_wire = None
        self.patch_callback = None
        self.delete_callback = None
        self.context_menu_callback = None
        self.query_volume_callback = None
        self.synth_volumes = {}
        self.synth_muted = {}

    def set_callbacks(self, patch_cb, delete_cb, context_menu_cb=None, query_vol_cb=None):
        self.patch_callback = patch_cb
        self.delete_callback = delete_cb
        self.context_menu_callback = context_menu_cb
        self.query_volume_callback = query_vol_cb

    def set_volume(self, synth_name, vol):
        self.synth_volumes[synth_name] = vol
        if synth_name in self.nodes:
            self.nodes[synth_name].set_volume_icon(self.synth_muted.get(synth_name, False))

    def set_muted(self, synth_name, is_muted):
        self.synth_muted[synth_name] = is_muted
        if synth_name in self.nodes:
            self.nodes[synth_name].set_volume_icon(is_muted)

    def update_patch_bay(self, synths: list, channels: list, patches: list, synth_colors=None):
        self._synths = synths
        self._channels = channels
        self._patches = patches
        self.synth_colors = synth_colors or {}
        
        for s in synths:
            if s not in self.synth_volumes and self.query_volume_callback:
                self.synth_volumes[s] = None
                self.query_volume_callback(s)

        self.relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scene.setSceneRect(0, 0, self.viewport().width(), self.viewport().height())
        self.relayout()

    def relayout(self):
        self.scene.clear()
        self.nodes.clear()
        view_width = self.viewport().width()

        # Draw Synths
        y_pos = 0
        for synth_name in self._synths:
            c = self.synth_colors.get(synth_name, QColor("#333333"))
            bg_color = QColor(c.red() // 3, c.green() // 3, c.blue() // 3)
            
            node = PatchNode(synth_name, "synth", self.node_width, self.node_height, color=bg_color)
            node.set_volume_icon(self.synth_muted.get(synth_name, False))
            node.setPos(0, y_pos)
            self.scene.addItem(node)
            self.nodes[synth_name] = node
            y_pos += self.node_height

        # Draw Channels
        y_pos = 0
        x_right = max(view_width - self.node_width, self.node_width + 50)
        for ch in self._channels:
            ch_name = f"Out {ch}"
            node = PatchNode(ch_name, "channel", self.node_width, self.node_height)
            node.setPos(x_right, y_pos)
            self.scene.addItem(node)
            self.nodes[ch_name] = node
            y_pos += self.node_height

        # Draw Patches
        for patch in self._patches:
            s_name = patch.get("synth")
            if s_name not in self.nodes: continue
            start_pos = self.nodes[s_name].get_port_position()

            for ch in patch.get("channels", []):
                ch_name = f"Out {ch}"
                if ch_name not in self.nodes: continue
                end_pos = self.nodes[ch_name].get_port_position()

                # Pass metadata into the wire so we know what to delete later
                wire = PatchWire(start_pos, end_pos, synth_name=s_name, channel_num=ch)
                if s_name in self.synth_colors:
                    wire.base_color = self.synth_colors[s_name]
                    wire.pen.setColor(wire.base_color)
                    wire.setPen(wire.pen)
                self.scene.addItem(wire)

    # --- Mouse & Keyboard Overrides ---
    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        while item and not isinstance(item, PatchNode):
            item = item.parentItem()

        if isinstance(item, PatchNode) and item.node_type == "synth":
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_start_node = item
                start_pos = item.get_port_position()
                scene_pos = self.mapToScene(event.pos())
                self.temp_wire = PatchWire(start_pos, scene_pos, is_temp=True)
                self.scene.addItem(self.temp_wire)
                return
            elif event.button() == Qt.MouseButton.RightButton:
                if self.context_menu_callback:
                    global_pos = event.globalPosition().toPoint()
                    self.context_menu_callback(item.name, global_pos)
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.temp_wire and self.drag_start_node:
            scene_pos = self.mapToScene(event.pos())
            start_pos = self.drag_start_node.get_port_position()
            self.temp_wire.update_positions(start_pos, scene_pos)

            # Node Hover Logic
            item = self.itemAt(event.pos())
            while item and not isinstance(item, PatchNode):
                item = item.parentItem()

            if isinstance(item, PatchNode) and item.node_type == "channel":
                if self.hovered_node != item:
                    if self.hovered_node: self.hovered_node.set_highlight(False)
                    self.hovered_node = item
                    self.hovered_node.set_highlight(True)
            else:
                if self.hovered_node:
                    self.hovered_node.set_highlight(False)
                    self.hovered_node = None
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.temp_wire:
            self.scene.removeItem(self.temp_wire)
            self.temp_wire = None

            if self.hovered_node:
                self.hovered_node.set_highlight(False)
                synth_name = self.drag_start_node.name
                channel_num = self.hovered_node.name.replace("Out ", "")
                if self.patch_callback:
                    self.patch_callback(synth_name, channel_num)
                self.hovered_node = None

            self.drag_start_node = None
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """Deletes selected wires when Backspace/Delete is hit."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for item in self.scene.selectedItems():
                if isinstance(item, PatchWire) and self.delete_callback:
                    self.delete_callback(item.synth_name, item.channel_num)
        super().keyPressEvent(event)


from PyQt6.QtWidgets import QColorDialog
from PyQt6.QtCore import pyqtSignal

class SynthLabel(QLabel):
    clicked = pyqtSignal(str)
    color_changed = pyqtSignal(str, QColor)
    visibility_toggled = pyqtSignal(str, bool)

    def __init__(self, name, color, parent=None):
        super().__init__(name, parent)
        self.synth_name = name
        self.synth_color = color
        self.is_active_trigger = False
        self.is_visible_on_scope = True
        
        self.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContentsMargins(10, 5, 10, 5)
        self.update_style()
        
    def set_active_trigger(self, is_active):
        self.is_active_trigger = is_active
        self.update_style()
        
    def set_color(self, color):
        self.synth_color = color
        self.update_style()

    def update_style(self):
        bg = self.synth_color.name() if self.is_active_trigger else "#333333"
        fg = "#000000" if self.is_active_trigger else self.synth_color.name()
        
        if not self.is_visible_on_scope:
            bg = "#222222"
            fg = "#555555"
            
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border-radius: 4px;
            }}
        """)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.synth_name != "Free Run" and not self.is_visible_on_scope:
                return # Can't trigger on hidden
            self.clicked.emit(self.synth_name)
        elif event.button() == Qt.MouseButton.RightButton and self.synth_name != "Free Run":
            menu = QMenu(self)
            
            vis_widget = QWidget()
            vis_layout = QHBoxLayout(vis_widget)
            vis_layout.setContentsMargins(10, 5, 10, 5)
            
            vis_checkbox = QCheckBox("Visible on Scope")
            vis_checkbox
            vis_checkbox.setChecked(self.is_visible_on_scope)
            
            def on_vis_toggled(checked):
                self.is_visible_on_scope = checked
                if not self.is_visible_on_scope and self.is_active_trigger:
                    self.clicked.emit("Free Run")
                self.visibility_toggled.emit(self.synth_name, self.is_visible_on_scope)
                self.update_style()
                
            vis_checkbox.toggled.connect(on_vis_toggled)
            vis_layout.addWidget(vis_checkbox)
            
            vis_action = QWidgetAction(menu)
            vis_action.setDefaultWidget(vis_widget)
            menu.addAction(vis_action)
            
            change_color_action = menu.addAction("Change Color")
            
            action = menu.exec(event.globalPosition().toPoint())
            
            if action == change_color_action:
                color = QColorDialog.getColor(self.synth_color, None, "Select Synth Color")
                if color.isValid():
                    self.set_color(color)
                    self.color_changed.emit(self.synth_name, color)


class MultiScopeWidget(QWidget):
    trigger_level_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.samples_dict = {}  # { name: samples }
        self.colors_dict = {}   # { name: color }
        self.visible_synths = set()
        self.fractional_offset = 0.0
        
        self.trigger_level = 0.0
        self._dragging_trigger = False
        
    def update_samples(self, samples_dict, colors_dict, visible_synths, fractional_offset=0.0):
        self.samples_dict = samples_dict
        self.colors_dict = colors_dict
        self.visible_synths = visible_synths
        self.fractional_offset = fractional_offset
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging_trigger = True
            self._update_trigger_from_mouse(event.pos())
            
    def mouseMoveEvent(self, event):
        if self._dragging_trigger:
            self._update_trigger_from_mouse(event.pos())
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging_trigger = False
            
    def _update_trigger_from_mouse(self, pos):
        rect = self.rect()
        mid_y = rect.height() / 2.0
        val = (mid_y - pos.y()) / max(1, (mid_y - 5))
        self.trigger_level = max(-1.0, min(1.0, val))
        self.trigger_level_changed.emit(self.trigger_level)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        
        painter.fillRect(rect, QColor("#1e1e1e"))
        painter.setPen(QColor("#333"))
        painter.drawRect(0, 0, rect.width() - 1, rect.height() - 1)
        
        width = rect.width()
        height = rect.height()
        mid_y = height / 2.0
        
        trig_y = mid_y - (self.trigger_level * (mid_y - 5))
        pen = QPen(QColor("#ffffff"))
        pen.setStyle(Qt.PenStyle.DotLine)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(0, int(trig_y), int(width), int(trig_y))
        
        for name, samples in self.samples_dict.items():
            if name not in self.visible_synths or not samples:
                continue
                
            color = self.colors_dict.get(name, QColor("#00ff00"))
            painter.setPen(QPen(color, 1))
            
            path = QPainterPath()
            num_samples = len(samples)
            if num_samples <= 1:
                continue
                
            x_step = width / max(1, num_samples - 2)
            x_shift = -self.fractional_offset * x_step
            
            for i, val in enumerate(samples):
                x = (i * x_step) + x_shift
                y = mid_y - (max(-1.0, min(1.0, val)) * (mid_y - 5))
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
                    
            painter.drawPath(path)


class ConnectionStatusLabel(QLabel):
    def __init__(self, name, launch_callback, parent=None):
        super().__init__(f"{name}: Disconnected", parent)
        self.name = name
        self.launch_callback = launch_callback
        self.setStyleSheet("color: #ff5555;")
        self.setFont(QFont("Consolas", 10))
        
    def set_connected(self, connected, extra_text=""):
        if connected:
            self.setText(f"{self.name}: Connected {extra_text}")
            self.setStyleSheet("color: #4EC9B0;")
        else:
            self.setText(f"{self.name}: Disconnected")
            self.setStyleSheet("color: #ff5555;")
            
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            menu
            launch_action = menu.addAction(f"Launch {self.name}")
            action = menu.exec(event.globalPosition().toPoint())
            if action == launch_action:
                self.launch_callback()

class TelemetryBay(QWidget):
    color_changed = pyqtSignal(str, QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)
        
        # Toolbar
        self.toolbar_widget = QWidget()
        self.toolbar = QHBoxLayout(self.toolbar_widget)
        self.toolbar.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.toolbar_widget)
        
        self.labels = {}
        self.free_run_label = SynthLabel("Free Run", QColor("#888888"))
        self.free_run_label.set_active_trigger(True)
        self.free_run_label.clicked.connect(self.set_trigger_source)
        self.toolbar.addWidget(self.free_run_label)
        self.toolbar.addStretch()
        
        self.trigger_source = "Free Run"
        
        # Multi Scope
        self.scope = MultiScopeWidget()
        self.layout.addWidget(self.scope, stretch=1)
        
        # Timebase slider
        self.timebase_slider = QSlider(Qt.Orientation.Horizontal)
        self.timebase_slider.setRange(100, 8192)
        self.timebase_slider.setValue(1024)
        self.layout.addWidget(self.timebase_slider)
        
        self.unified_buffer = {}  # { synth_name: { block_index: samples } }
        self.last_block_index = 0
        self.visible_synths = set()
        self.synth_colors = {}
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.repaint_scopes)
        self.timer.start(33)
        
    def set_trigger_source(self, name):
        self.trigger_source = name
        self.free_run_label.set_active_trigger(name == "Free Run")
        for lbl_name, lbl in self.labels.items():
            lbl.set_active_trigger(lbl_name == name)
            
    def _on_color_changed(self, name, color):
        self.synth_colors[name] = color
        self.color_changed.emit(name, color)
        
    def _on_visibility_toggled(self, name, is_visible):
        if is_visible:
            self.visible_synths.add(name)
        else:
            self.visible_synths.discard(name)
            
    def push_telemetry(self, synth_name, block_index, samples):
        if synth_name not in self.unified_buffer:
            self.unified_buffer[synth_name] = collections.deque(maxlen=16)
        self.unified_buffer[synth_name].append((block_index, samples))
            
        self.last_block_index = max(self.last_block_index, block_index)
        
    def sync_synths(self, active_synths, synth_colors):
        self.synth_colors = synth_colors
        
        current = set(self.labels.keys())
        active = set(active_synths)
        for name in current - active:
            lbl = self.labels.pop(name)
            self.toolbar.removeWidget(lbl)
            lbl.deleteLater()
            self.visible_synths.discard(name)
            if self.trigger_source == name:
                self.set_trigger_source("Free Run")
                
        new_synths = []
        for name in active - current:
            color = self.synth_colors.get(name, QColor("#00ff00"))
            lbl = SynthLabel(name, color)
            lbl.clicked.connect(self.set_trigger_source)
            lbl.color_changed.connect(self._on_color_changed)
            lbl.visibility_toggled.connect(self._on_visibility_toggled)
            self.toolbar.insertWidget(self.toolbar.count() - 1, lbl)
            self.labels[name] = lbl
            self.visible_synths.add(name)
            new_synths.append(name)
            
        for name in current.intersection(active):
            self.labels[name].set_color(self.synth_colors[name])
            
        return new_synths
        
    def _assemble_flat_buffer(self, synth_name, blocks_to_fetch, anchor_block):
        if synth_name not in self.unified_buffer:
            return []
            
        buf = self.unified_buffer[synth_name]
        buf_dict = {b: s for b, s in buf}
        blocks_to_concat = []
        
        for b in range(anchor_block, anchor_block - blocks_to_fetch, -1):
            if b in buf_dict:
                blocks_to_concat.append(buf_dict[b])
            else:
                blocks_to_concat.append([0.0] * 1024)
                
        blocks_to_concat.reverse()
        
        return list(itertools.chain.from_iterable(blocks_to_concat))

    def repaint_scopes(self):
        timebase = self.timebase_slider.value()
        level = self.scope.trigger_level
        
        anchor_block = self.last_block_index
        blocks_needed = (timebase // 1024) + 2
        
        display_dict = {}
        fractional_offset = 0.0
        
        if self.trigger_source == "Free Run" or self.trigger_source not in self.unified_buffer:
            for name in self.visible_synths:
                flat = self._assemble_flat_buffer(name, blocks_needed, anchor_block)
                if len(flat) > timebase + 1:
                    flat = flat[-(timebase + 1):]
                display_dict[name] = flat
        else:
            source_flat = self._assemble_flat_buffer(self.trigger_source, blocks_needed, anchor_block)
            if source_flat:
                trigger_index = -1
                hysteresis_margin = 0.05
                
                for i in range(len(source_flat) - 1, 0, -1):
                    if source_flat[i-1] <= level and source_flat[i] > level:
                        valid_trigger = False
                        for j in range(i-1, -1, -1):
                            if source_flat[j] < level - hysteresis_margin:
                                valid_trigger = True
                                break
                            elif source_flat[j] > level:
                                break
                                
                        if valid_trigger:
                            trigger_index = i
                            if len(source_flat) - trigger_index >= timebase:
                                y0 = source_flat[i-1]
                                y1 = source_flat[i]
                                if y1 != y0:
                                    fractional_offset = (level - y0) / (y1 - y0)
                                break
                            else:
                                trigger_index = -1
                                
                if trigger_index == -1:
                    trigger_index = max(0, len(source_flat) - timebase)
                    
                for name in self.visible_synths:
                    flat = self._assemble_flat_buffer(name, blocks_needed, anchor_block)
                    if trigger_index < len(flat):
                        sliced = flat[trigger_index : trigger_index + timebase + 1]
                        display_dict[name] = sliced
                        
        self.scope.update_samples(display_dict, self.synth_colors, self.visible_synths, fractional_offset)
        self.scope.update()

class WorkerSignals(QObject):
    frame_ready = pyqtSignal(QImage)

class VideoDecoderTask(QRunnable):
    def __init__(self, jpeg_data, target_size):
        super().__init__()
        self.jpeg_data = jpeg_data
        self.target_size = target_size
        self.signals = WorkerSignals()

    def run(self):
        image = QImage()
        if image.loadFromData(self.jpeg_data):
            scaled_image = image.scaled(
                self.target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.signals.frame_ready.emit(scaled_image)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.current_filepath = None
        self.update_window_title()
        self.resize(1600, 1000)
        
        self.synth_colors = {}
        self.color_palette = [ # Color names from Novation LaunchControl XL
            QColor("#4bfd58"), # Vibrant Green
            QColor("#18d7ff"), # Vibrant Light Blue
            QColor("#1f56da"), # Vibrant Dark Blue
            QColor("#9635ff"), # Vibrant Purple
            QColor("#f226fe"), # Vibrant Fuschia
            QColor("#ff0100"), # Vibrant Red
            QColor("#ff881b"), # Vibrant Orange
            QColor("#faff06")  # Vibrant Yellow
        ]

        # Enable freeform docking
        self.setDockNestingEnabled(True)
        self.setCentralWidget(QWidget())
        self.centralWidget().hide()

        self.setup_docks()
        self.setup_menu()

        # Layout memory
        self.settings = QSettings("Zeloof Designworks", "OSCAR IDE")
        self.load_layout()
        self.setup_status_bar()
        self.setup_oscar_environment()
        self.setup_network()
        self.setup_shortcuts()
        self.setup_video_network()

        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.check_engine_connection)
        self.reconnect_timer.start(2000)  # Check every 2 seconds

        self.stdout_buffer = ""
        self.pending_context_menu = None
        
        self.editor_widget.modificationChanged.connect(self.update_window_title)

    def check_unsaved_changes(self) -> bool:
        """Returns True if it's safe to proceed, False if cancelled."""
        if not self.editor_widget.isModified():
            return True
            
        if not self.current_filepath and not self.editor_widget.text().strip():
            return True

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Would you like to save them?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save
        )

        if reply == QMessageBox.StandardButton.Save:
            self.save_file()
            return not self.editor_widget.isModified()
        elif reply == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    def closeEvent(self, event):
        if hasattr(self, 'engine_process'):
            self.engine_process.terminate()
            self.engine_process.waitForFinished(1000)
        if hasattr(self, 'render_process'):
            self.render_process.terminate()
            self.render_process.waitForFinished(1000)

        if self.check_unsaved_changes():
            self.save_layout()
            event.accept()
        else:
            event.ignore()

    def setup_oscar_environment(self):
        if self.settings.contains("oscar_render_path"):
            self.oscar_render_path = self.settings.value("oscar_render_path")
        else:
            self.settings.setValue("oscar_render_path", "oscar_render")
            self.oscar_render_path = self.settings.value("oscar_render_path")

        if self.settings.contains("oscar_engine_path"):
            self.oscar_engine_path = self.settings.value("oscar_engine_path")
        else:
            self.settings.setValue("oscar_engine_path", "oscar_engine")
            self.oscar_engine_path = self.settings.value("oscar_engine_path")

        if self.settings.contains("telemetry_port"):
            self.telemetry_port = int(self.settings.value("telemetry_port"))
        else:
            self.settings.setValue("telemetry_port", 9393)
            self.telemetry_port = 9393

    def create_interactive_patch(self, synth_name, channel_num):
        patch_name = f"p_{synth_name}_{channel_num}"
        cmd = f"Patch('{patch_name}', '{synth_name}', [{channel_num}])"
        self.console_output.appendPlainText(f"\n> {cmd}  [UI Patch]")

        if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
            self.oscar_socket.write((cmd + '\n').encode('utf-8'))

    def delete_interactive_patch(self, synth_name, channel_num):
        """Generates a Python loop to disconnect a specific channel from a synth."""
        cmd = (
            f"for p in ACTIVE_PATCHES.values():\n"
            f"    if p.synth() == '{synth_name}' and {channel_num} in p.ch():\n"
            f"        p.ch([c for c in p.ch() if c != {channel_num}])\n"
        )
        self.console_output.appendPlainText(f"\n> Disconnecting {synth_name} from Out {channel_num} [UI Delete]")

        if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
            self.oscar_socket.write((cmd + '\n').encode('utf-8'))

    def show_synth_context_menu(self, synth_name, global_pos):
        self.pending_context_menu = (synth_name, global_pos)
        cmd = f"print(f'__VOL__:{synth_name}:{{{synth_name}.amp()}}')"
        if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
            self.oscar_socket.write((cmd + '\n').encode('utf-8'))

    def _show_synth_context_menu_with_vol(self, synth_name, global_pos, vol):
        menu = QMenu(self)
        menu

        vol_widget = QWidget()
        vol_layout = QHBoxLayout(vol_widget)
        vol_layout.setContentsMargins(10, 5, 10, 5)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 1000) 
        slider.setValue(int(vol * 1000))
        
        spinbox = QDoubleSpinBox()
        spinbox.setRange(0.0, 1.0)
        spinbox.setSingleStep(0.01)
        spinbox.setValue(vol)
        spinbox

        mute_checkbox = QCheckBox("Mute")
        mute_checkbox
        mute_checkbox.setChecked(self.patch_bay_widget.synth_muted.get(synth_name, False))

        def on_vol_changed(v):
            self.patch_bay_widget.set_volume(synth_name, v)
            cmd = f"{synth_name}.amp({v})"
            if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
                self.oscar_socket.write((cmd + '\n').encode('utf-8'))

        slider.valueChanged.connect(lambda v: spinbox.setValue(v / 1000.0))
        spinbox.valueChanged.connect(lambda v: slider.setValue(int(v * 1000)))
        spinbox.valueChanged.connect(on_vol_changed)
        
        def on_mute_toggled(checked):
            self.patch_bay_widget.set_muted(synth_name, checked)
            cmd = f"{synth_name}.mute({'True' if checked else 'False'})"
            if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
                self.oscar_socket.write((cmd + '\n').encode('utf-8'))
                
        mute_checkbox.toggled.connect(on_mute_toggled)

        vol_label = QLabel("Vol:")
        vol_label
        
        vol_layout.addWidget(vol_label)
        vol_layout.addWidget(slider)
        vol_layout.addWidget(spinbox)
        vol_layout.addWidget(mute_checkbox)

        vol_action = QWidgetAction(menu)
        vol_action.setDefaultWidget(vol_widget)
        menu.addAction(vol_action)

        menu.exec(global_pos)


    def check_engine_connection(self):
        """Silently auto-reconnects to the OSCAR engine if the connection is lost."""
        if self.oscar_socket.state() == QTcpSocket.SocketState.UnconnectedState:
            self.oscar_socket.connectToHost("localhost", 5555)

    def setup_status_bar(self):
        self.status_bar = self.statusBar()
        self.status_bar
        
        self.cpu_label = QLabel("CPU: 0.0%")
        self.cpu_label.setFont(QFont("Consolas", 10))
        self.status_bar.addWidget(self.cpu_label)
        
        self.engine_status = ConnectionStatusLabel("Engine", self.launch_engine)
        self.status_bar.addPermanentWidget(self.engine_status)
        
        self.render_status = ConnectionStatusLabel("Renderer", self.launch_render)
        self.status_bar.addPermanentWidget(self.render_status)
        
        # CPU Monitor Timer
        self.prev_idle = 0
        self.prev_total = 0
        self.cpu_timer = QTimer(self)
        self.cpu_timer.timeout.connect(self.update_cpu_load)
        self.cpu_timer.start(1000)
        
        self.frames_received = 0
        self.fps_timer = QTimer(self)
        self.fps_timer.timeout.connect(self.update_fps)
        self.fps_timer.start(1000)
        
    def update_cpu_load(self):
        try:
            import psutil
            load = psutil.cpu_percent(interval=None)
            self.cpu_label.setText(f"CPU: {load:.1f}%")
        except Exception:
            self.cpu_label.setText("CPU: N/A")
            
    def update_fps(self):
        if hasattr(self, 'video_socket') and self.video_socket.state() == QTcpSocket.SocketState.ConnectedState:
            self.render_status.set_connected(True, f"({self.frames_received} FPS)")
        self.frames_received = 0

    def setup_video_network(self):
        """Spins up a local server to receive JPEGs from the C++ renderer."""
        self.expected_video_size = 0
        self.video_server = QTcpServer(self)
        self.video_server.listen(QHostAddress.SpecialAddress.LocalHost, 5557)
        self.video_server.newConnection.connect(self.accept_video_connection)

    def accept_video_connection(self):
        self.video_socket = self.video_server.nextPendingConnection()
        self.video_socket.readyRead.connect(self.read_video_frame)
        
        def safe_video_disconnect():
            try:
                self.render_status.set_connected(False)
            except RuntimeError:
                pass
                
        self.video_socket.disconnected.connect(safe_video_disconnect)
        self.expected_video_size = 0
        self.console_output.appendPlainText("--- Renderer Video Feed Connected ---")
        self.render_status.set_connected(True, "(0 FPS)")

    def read_video_frame(self):
        """Reads the framed TCP stream, decodes the JPEG in a background thread."""
        while True:
            # Read the 4-byte header if we are waiting for a new frame
            if self.expected_video_size == 0:
                if self.video_socket.bytesAvailable() >= 4:
                    header = self.video_socket.read(4)
                    self.expected_video_size = int.from_bytes(header, byteorder='big')
                else:
                    break  # Wait for more bytes

            # Wait until the full JPEG payload has arrived
            if self.expected_video_size > 0:
                if self.video_socket.bytesAvailable() >= self.expected_video_size:
                    jpeg_data = self.video_socket.read(self.expected_video_size)
                    self.expected_video_size = 0  # Reset state for the next frame

                    # Decode and scale in background
                    self.frames_received += 1
                    task = VideoDecoderTask(jpeg_data, self.preview_label.size())
                    task.signals.frame_ready.connect(self._on_frame_decoded)
                    QThreadPool.globalInstance().start(task)
                else:
                    break  # Payload is partially here, wait for the rest

    def _on_frame_decoded(self, image):
        self.preview_label.setPixmap(QPixmap.fromImage(image))

    def setup_shortcuts(self):
        # Bind Ctrl+Enter (Return) to execute code
        self.run_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.run_shortcut.activated.connect(self.execute_editor_code)

        # Also bind the numpad Enter just in case
        self.run_shortcut_num = QShortcut(QKeySequence("Ctrl+Enter"), self)
        self.run_shortcut_num.activated.connect(self.execute_editor_code)

    def setup_network(self):
        self.oscar_socket = QTcpSocket(self)
        self.oscar_socket.connected.connect(
            lambda: self.console_output.appendPlainText("--- IDE Connected to OSCAR Engine ---"))
        self.oscar_socket.connected.connect(lambda: self.engine_status.set_connected(True))
        
        def safe_disconnect():
            try:
                self.console_output.appendPlainText("--- Disconnected from OSCAR ---")
                self.engine_status.set_connected(False)
            except RuntimeError:
                pass
                
        self.oscar_socket.disconnected.connect(safe_disconnect)
        self.oscar_socket.readyRead.connect(self.read_oscar_stdout)

        # Connect to the engine
        self.oscar_socket.connectToHost("localhost", 5555)

        # Wire up the console input box
        self.console_input.returnPressed.connect(self.send_console_command)
        
        # UDP Telemetry Socket
        self.udp_socket = QUdpSocket(self)
        self.udp_socket.bind(QHostAddress.SpecialAddress.LocalHost, getattr(self, 'telemetry_port', 9393))
        self.udp_socket.readyRead.connect(self.read_telemetry)

    def read_telemetry(self):
        while self.udp_socket.hasPendingDatagrams():
            datagram, host, port = self.udp_socket.readDatagram(self.udp_socket.pendingDatagramSize())
            if len(datagram) < 48:
                continue
            
            header = datagram[:48]
            try:
                synth_name_b, num_samples, block_index = struct.unpack("<32si4xQ", header)
                synth_name = synth_name_b.decode('utf-8').rstrip('\x00')
                
                expected_size = 48 + (num_samples * 4)
                if len(datagram) >= expected_size:
                    samples = struct.unpack(f"<{num_samples}f", datagram[48:expected_size])
                    self.telemetry_bay_widget.push_telemetry(synth_name, block_index, samples)
            except Exception:
                pass

    def execute_editor_code(self):
        """Intelligently grabs code blocks and fires them to the OSCAR engine."""
        if self.editor_widget.hasSelectedText():
            # User has highlighted text. Snap to the full lines.
            line_from, index_from, line_to, index_to = self.editor_widget.getSelection()
            start_line = line_from
            # If they highlighted to the exact beginning of the next line, don't include that empty line
            end_line = line_to if index_to > 0 else max(line_from, line_to - 1)
        else:
            # No selection. Use Lexer folding logic.
            line, _ = self.editor_widget.getCursorPosition()

            if not self.editor_widget.text(line).strip():
                return

            # Walk up to find the root parent
            current_parent = self.editor_widget.SendScintilla(QsciScintilla.SCI_GETFOLDPARENT, line)
            top_parent = line if current_parent < 0 else current_parent
            while current_parent >= 0:
                top_parent = current_parent
                current_parent = self.editor_widget.SendScintilla(QsciScintilla.SCI_GETFOLDPARENT, top_parent)

            # Find the last child of this root block
            last_child = self.editor_widget.SendScintilla(QsciScintilla.SCI_GETLASTCHILD, top_parent, -1)

            if last_child > top_parent:
                start_line = top_parent
                end_line = last_child

                # Peek ahead to catch orphaned closing brackets
                scan_line = end_line + 1
                while scan_line < self.editor_widget.lines():
                    next_text = self.editor_widget.text(scan_line).strip()
                    if not next_text:
                        scan_line += 1
                    elif next_text in (']', ')', '}', '],', '),', '},', '"""', "'''"):
                        end_line = scan_line
                        scan_line += 1
                    else:
                        break
            else:
                start_line = line
                end_line = line

        # Trigger the visual flash feedback
        self.editor_widget.flash_lines(start_line, end_line)

        # Extract the actual text for the block
        code_lines = []
        for l in range(start_line, end_line + 1):
            code_lines.append(self.editor_widget.text(l).rstrip('\r\n'))

        code_to_run = '\n'.join(code_lines)
        if not code_to_run.strip(): return

        # Echo preview to local console
        preview = code_to_run if len(code_lines) < 4 else f"{code_lines[0]} ... [Executed {len(code_lines)} lines]"
        self.console_output.appendPlainText(f"\n> {preview}")

        # Send it to the engine
        if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
            payload = code_to_run + '\n'
            self.oscar_socket.write(payload.encode('utf-8'))
        else:
            self.console_output.appendPlainText("! Not connected to OSCAR. Retrying connection...")
            self.oscar_socket.connectToHost("localhost", 5555)

    def read_oscar_stdout(self):
        """Receives live prints from the OSCAR engine and intercepts UI state syncs."""
        if not hasattr(self, 'stdout_bytes_buffer'):
            self.stdout_bytes_buffer = b""
            
        self.stdout_bytes_buffer += self.oscar_socket.readAll().data()

        # Process complete lines one by one
        while b'\n' in self.stdout_bytes_buffer:
            line_bytes, self.stdout_bytes_buffer = self.stdout_bytes_buffer.split(b'\n', 1)
            try:
                line = line_bytes.decode('utf-8')
            except UnicodeDecodeError:
                continue


            # Did the engine send a hidden UI update?
            if line.startswith("__STATE_SYNC__:"):
                json_str = line.replace("__STATE_SYNC__:", "").strip()
                try:
                    state = json.loads(json_str)
                    synths = state.get('synths', [])
                    
                    for s in synths:
                        self.get_synth_color(s)
                    self.editor_widget.update_synth_highlights(self.synth_colors)
                    
                    self.patch_bay_widget.update_patch_bay(
                        synths,
                        state.get('channels', []),
                        state.get('patches', []),
                        self.synth_colors
                    )
                    
                    new_synths = self.telemetry_bay_widget.sync_synths(synths, self.synth_colors)
                    if new_synths and self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
                        for s in new_synths:
                            self.oscar_socket.write((f"{s}.visualize(True)\n").encode('utf-8'))
                except Exception as e:
                    self.console_output.appendPlainText(f"! UI Sync Error: {str(e)}\n")
            elif line.startswith("__VOL__:"):
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    synth_name = parts[1]
                    try:
                        vol = float(parts[2])
                        self.patch_bay_widget.set_volume(synth_name, vol)
                        if self.pending_context_menu and self.pending_context_menu[0] == synth_name:
                            pos = self.pending_context_menu[1]
                            self.pending_context_menu = None
                            self._show_synth_context_menu_with_vol(synth_name, pos, vol)
                    except ValueError:
                        pass
            else:
                # Standard print statement, echo it to the console
                self.console_output.appendPlainText(line)

    def send_console_command(self):
        """Sends a single line command to the OSCAR REPL."""
        cmd = self.console_input.text()
        if not cmd: return

        self.console_output.appendPlainText(f"> {cmd}")
        self.console_input.clear()

        if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
            self.oscar_socket.write((cmd + '\n').encode('utf-8'))
        else:
            self.console_output.appendPlainText("! Not connected. Retrying...")
            self.oscar_socket.connectToHost("localhost", 5555)

    def update_window_title(self):
        title = "OSCAR IDE"
        if self.current_filepath:
            filename = os.path.basename(self.current_filepath)
            title = f"{title} - {filename}"
        if hasattr(self, 'editor_widget') and self.editor_widget.isModified():
            title += " *"
        self.setWindowTitle(title)

    def setup_menu(self):
        self.setup_file_menu()
        self.setup_edit_menu()
        self.setup_window_menu()
        self.setup_oscar_menu()
        self.setup_help_menu()

    def setup_window_menu(self):
        window_menu = self.menuBar().addMenu("Window")
        
        window_menu.addAction(self.editor_dock.toggleViewAction())
        window_menu.addAction(self.console_dock.toggleViewAction())
        window_menu.addAction(self.preview_dock.toggleViewAction())
        window_menu.addAction(self.patch_dock.toggleViewAction())
        window_menu.addAction(self.telemetry_dock.toggleViewAction())



        font_action = QAction("Editor Font...", self)
        font_action.triggered.connect(self.select_editor_font)
        window_menu.addAction(font_action)

    def select_editor_font(self):
        from PyQt6.QtWidgets import QFontDialog
        font, ok = QFontDialog.getFont(self.editor_widget.font(), None, "Select Editor Font")
        if ok:
            self.editor_widget.setFont(font)
            self.editor_widget.setMarginsFont(font)
            self.editor_widget.lexer.setDefaultFont(font)

    def setup_file_menu(self):
        file_menu = self.menuBar().addMenu("File")

        # --- File I/O Actions ---
        new_action = QAction("New File", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_file)
        file_menu.addAction(new_action)

        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as_file)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        save_layout_action = QAction("Save Window Layout", self)
        save_layout_action.triggered.connect(self.save_layout)
        file_menu.addAction(save_layout_action)

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def setup_edit_menu(self):
        edit_menu = self.menuBar().addMenu("Edit")

    def setup_help_menu(self):
        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def show_about_dialog(self):
        about_dialog = QDialog(self)
        about_dialog.setWindowTitle("About OSCAR IDE")
        about_dialog.setFixedSize(400, 200)
        layout = QVBoxLayout(about_dialog)
        text = QLabel("""
OSCAR IDE
Version 0.1
by Zeloof Designworks, LLC
""")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text)
        about_dialog.exec()

    def setup_oscar_menu(self):
        oscar_menu = self.menuBar().addMenu("OSCAR")

        oscar_settings_action = QAction("OSCAR Settings", self)
        oscar_settings_action.triggered.connect(self.show_oscar_settings)
        oscar_menu.addAction(oscar_settings_action)

        oscar_menu.addSeparator()

        launch_engine_action = QAction("Launch Engine", self)
        launch_engine_action.triggered.connect(self.launch_engine)
        oscar_menu.addAction(launch_engine_action)

        launch_render_action = QAction("Launch Render", self)
        launch_render_action.triggered.connect(self.launch_render)
        oscar_menu.addAction(launch_render_action)

    def save_oscar_settings(self, renderer_path, engine_path, telemetry_port, dialog):
        self.settings.setValue("oscar_render_path", renderer_path)
        self.settings.setValue("oscar_engine_path", engine_path)
        self.settings.setValue("telemetry_port", int(telemetry_port))
        self.oscar_render_path = renderer_path
        self.oscar_engine_path = engine_path
        self.telemetry_port = int(telemetry_port)
        dialog.accept()

    def show_oscar_settings(self):
        """Opens a pop-up window for OSCAR environment settings."""
        oscar_settings_dialog = QDialog(self)
        oscar_settings_dialog.setWindowTitle("OSCAR Settings")
        layout = QFormLayout()
        renderer_path_label = QLabel("OSCAR Renderer Path:")
        renderer_path_edit = QLineEdit(self.oscar_render_path)
        layout.addRow(renderer_path_label, renderer_path_edit)
        engine_path_label = QLabel("OSCAR Engine Path:")
        engine_path_edit = QLineEdit(self.oscar_engine_path)
        layout.addRow(engine_path_label, engine_path_edit)
        port_label = QLabel("Telemetry Port:")
        port_edit = QLineEdit(str(getattr(self, 'telemetry_port', 9393)))
        layout.addRow(port_label, port_edit)
        
        save_button = QPushButton("Save")
        save_button.clicked.connect(lambda: self.save_oscar_settings(renderer_path_edit.text(), engine_path_edit.text(), port_edit.text(), oscar_settings_dialog))
        layout.addWidget(save_button)
        oscar_settings_dialog.setLayout(layout)
        oscar_settings_dialog.exec()

    def launch_engine(self):
        if hasattr(self, 'engine_process') and self.engine_process.state() != QProcess.ProcessState.NotRunning:
            return
        self.console_output.appendPlainText(f"> Launching Engine: {self.oscar_engine_path}")
        self.engine_process = QProcess(self)
        self.engine_process.startCommand(self.oscar_engine_path)

    def launch_render(self):
        if hasattr(self, 'render_process') and self.render_process.state() != QProcess.ProcessState.NotRunning:
            return
        self.console_output.appendPlainText(f"> Launching Renderer: {self.oscar_render_path}")
        self.render_process = QProcess(self)
        self.render_process.startCommand(self.oscar_render_path)

    # --- File Handling Methods ---
    def new_file(self):
        if not self.check_unsaved_changes():
            return
        self.editor_widget.clear()
        self.current_filepath = None
        self.editor_widget.setModified(False)
        self.update_window_title()

    def open_file(self):
        if not self.check_unsaved_changes():
            return
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", "OSCAR Files (*.os);;Python Files (*.py);;All Files (*)"
        )
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.editor_widget.setText(content)
                self.current_filepath = filepath
                self.editor_widget.setModified(False)
                self.update_window_title()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not open file:\n{str(e)}")

    def save_file(self):
        if not self.current_filepath:
            self.save_as_file()
        else:
            self._write_to_file(self.current_filepath)

    def save_as_file(self):
        filepath, _ = QFileDialog.getSaveFileName(
            None, "Save File", "", "OSCAR Files (*.os);;Python Files (*.py);;All Files (*)"
        )
        if filepath:
            self.current_filepath = filepath
            self._write_to_file(filepath)
            self.update_window_title()

    def _write_to_file(self, filepath):
        try:
            content = self.editor_widget.text()
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            self.console_output.appendPlainText(f"> Saved {filepath}")
            self.editor_widget.setModified(False)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{str(e)}")

    # --- Layout Methods ---
    def save_layout(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())

    def load_layout(self):
        if self.settings.value("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
        if self.settings.value("windowState"):
            self.restoreState(self.settings.value("windowState"))
            
    def get_synth_color(self, synth_name):
        if synth_name not in self.synth_colors:
            idx = len(self.synth_colors) % len(self.color_palette)
            self.synth_colors[synth_name] = self.color_palette[idx]
        return self.synth_colors[synth_name]

    def query_synth_volume(self, synth_name):
        cmd = f"print(f'__VOL__:{synth_name}:{{{synth_name}.amp()}}')"
        if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
            self.oscar_socket.write((cmd + '\n').encode('utf-8'))

    def _on_telemetry_color_changed(self, synth_name, color):
        self.synth_colors[synth_name] = color
        self.editor_widget.update_synth_highlights(self.synth_colors)
        
        # Trigger an update on patch bay view
        self.patch_bay_widget.update_patch_bay(
            self.patch_bay_widget._synths,
            self.patch_bay_widget._channels,
            self.patch_bay_widget._patches,
            self.synth_colors
        )

    def setup_docks(self):
        # --- Editor Dock ---
        self.editor_dock = QDockWidget("Editor", self)
        self.editor_dock.setObjectName("EditorDock")
        self.editor_widget = ScintillaEditor()
        self.editor_dock.setWidget(self.editor_widget)
        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, self.editor_dock)

        # --- Console Dock ---
        self.console_dock = QDockWidget("Console", self)
        self.console_dock.setObjectName("ConsoleDock")

        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        console_layout.setContentsMargins(0, 0, 0, 0)

        self.console_output = QPlainTextEdit("> ready.\n")
        self.console_output.setReadOnly(True)

        self.console_input = QLineEdit(self)
        self.console_input.setPlaceholderText("Enter command...")

        console_layout.addWidget(self.console_output)
        console_layout.addWidget(self.console_input)
        self.console_dock.setWidget(console_widget)

        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.console_dock)

        # --- Preview & Patch Bay Docks ---
        self.preview_dock = QDockWidget("Preview", self)
        self.preview_dock.setObjectName("PreviewDock")
        self.preview_label = QLabel("Waiting for render feed...", alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setObjectName("PreviewLabel")
        self.preview_dock.setWidget(self.preview_label)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.preview_dock)

        self.patch_dock = QDockWidget("Patch Bay", self)
        self.patch_dock.setObjectName("PatchBayDock")

        self.patch_bay_widget = PatchBayView()
        self.patch_bay_widget.set_callbacks(self.create_interactive_patch, self.delete_interactive_patch, self.show_synth_context_menu, self.query_synth_volume)
        self.patch_dock.setWidget(self.patch_bay_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.patch_dock)

        self.telemetry_dock = QDockWidget("Telemetry", self)
        self.telemetry_dock.setObjectName("TelemetryDock")
        self.telemetry_bay_widget = TelemetryBay(self)
        self.telemetry_bay_widget.color_changed.connect(self._on_telemetry_color_changed)
        self.telemetry_dock.setWidget(self.telemetry_bay_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.telemetry_dock)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    font = app.font()
    font.setPointSize(12)
    app.setFont(font)

    window = MainWindow()

    import os
    style_path = os.path.join(os.path.dirname(__file__), "styles", "style.qss")
    if os.path.exists(style_path):
        with open(style_path, "r") as f:
            window.setStyleSheet(f.read())

    window.show()
    sys.exit(app.exec())