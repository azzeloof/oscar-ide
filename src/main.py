import sys
import os
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QDockWidget, QLineEdit, QDialog, QPlainTextEdit,
                             QLabel, QFileDialog, QMessageBox, QGraphicsView,
                             QGraphicsScene, QGraphicsPathItem,
                             QGraphicsRectItem, QGraphicsTextItem, QFormLayout,
                             QPushButton, QGridLayout, QMenu, QInputDialog,
                             QSlider, QDoubleSpinBox, QHBoxLayout, QWidgetAction,
                             QCheckBox)
from PyQt6.QtGui import (QAction, QColor, QFont, QShortcut, QKeySequence, QPixmap,
                         QPainterPath, QPen, QBrush, QColor, QPainter,
                         QPainterPathStroker)
from PyQt6.QtCore import Qt, QSettings, QTimer, QPointF, QRectF, QProcess
from PyQt6.Qsci import QsciScintilla, QsciLexerPython
from PyQt6.QtNetwork import QTcpSocket, QTcpServer, QHostAddress


class ScintillaEditor(QsciScintilla):
    """A fully-featured code editor widget using QScintilla."""

    def __init__(self):
        super().__init__()

        # Base Font setup
        editor_font = QFont("Consolas", 12)
        self.setFont(editor_font)
        self.setMarginsFont(editor_font)
        # Syntax Highlighting (The Lexer)
        self.lexer = QsciLexerPython()
        self.lexer.setDefaultFont(editor_font)
        self.lexer.setFont(editor_font, QsciLexerPython.Comment)

        # Customize Lexer colors for a VS Code-style dark theme
        self.lexer.setDefaultPaper(QColor("#1e1e1e"))  # Background
        self.lexer.setDefaultColor(QColor("#d4d4d4"))  # Default text
        self.lexer.setColor(QColor("#569cd6"), QsciLexerPython.Keyword)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.DoubleQuotedString)
        self.lexer.setColor(QColor("#ce9178"), QsciLexerPython.SingleQuotedString)
        self.lexer.setColor(QColor("#6a9955"), QsciLexerPython.Comment)
        self.lexer.setColor(QColor("#b5cea8"), QsciLexerPython.Number)
        self.lexer.setColor(QColor("#dcdcaa"), QsciLexerPython.Decorator)
        self.lexer.setColor(QColor("#dcdcaa"), QsciLexerPython.FunctionMethodName)
        self.lexer.setColor(QColor("#4EC9B0"), QsciLexerPython.ClassName)

        self.setLexer(self.lexer)

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

        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self._fade_flash)
        self.flash_alpha = 0
        self.flash_start_pos = 0
        self.flash_length = 0

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


from PyQt6.QtGui import QPainterPathStroker


class PatchWire(QGraphicsPathItem):
    """Draws a smooth, adaptive Bezier curve between nodes."""

    def __init__(self, start_pos, end_pos, synth_name=None, channel_num=None, is_temp=False):
        super().__init__()
        self.setZValue(-1)  # Keep wires behind nodes

        # Store metadata for deletion later
        self.synth_name = synth_name
        self.channel_num = channel_num

        self.pen = QPen(QColor("#4EC9B0"))
        self.pen.setWidth(2)

        if is_temp:
            self.pen.setStyle(Qt.PenStyle.DashLine)
            self.pen.setColor(QColor(78, 201, 176, 150))
        else:
            # Enable selection for permanent wires
            self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)

        self.setPen(self.pen)
        self.update_positions(start_pos, end_pos)

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
                self.pen.setColor(QColor("#4EC9B0"))
                self.pen.setWidth(2)
            self.setPen(self.pen)
        return super().itemChange(change, value)


class PatchNode(QGraphicsRectItem):
    """A dense, list-style node representing a Synth or a Channel."""

    def __init__(self, name, node_type="synth", width=100, height=26):
        super().__init__(0, 0, width, height)
        self.name = name
        self.node_type = node_type

        self.setBrush(QBrush(QColor("#333333")))
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
            self.setBrush(QBrush(QColor("#444444")))  # Lighten background
        else:
            self.setPen(QPen(QColor("#1e1e1e"), 1))
            self.setBrush(QBrush(QColor("#333333")))


class PatchBayView(QGraphicsView):
    """The main widget containing the interactive node scene."""

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.setStyleSheet("border: none;")
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

    def update_patch_bay(self, synths: list, channels: list, patches: list):
        self._synths = synths
        self._channels = channels
        self._patches = patches
        
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
            node = PatchNode(synth_name, "synth", self.node_width, self.node_height)
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.current_filepath = None
        self.update_window_title()
        self.resize(1600, 1000)

        # Enable freeform docking
        self.setDockNestingEnabled(True)
        self.setCentralWidget(QWidget())
        self.centralWidget().hide()

        self.setup_docks()
        self.setup_menu()

        # Layout memory
        self.settings = QSettings("Zeloof Designworks", "OSCAR IDE")
        self.load_layout()
        self.setup_oscar_environment()
        self.setup_network()
        self.setup_shortcuts()
        self.setup_video_network()

        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.check_engine_connection)
        self.reconnect_timer.start(2000)  # Check every 2 seconds

        self.stdout_buffer = ""
        self.pending_context_menu = None

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
        menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #d4d4d4; border: 1px solid #444; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background-color: #4EC9B0; color: #1e1e1e; }
        """)

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
        spinbox.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #444;
            }
        """)

        mute_checkbox = QCheckBox("Mute")
        mute_checkbox.setStyleSheet("color: #d4d4d4;")
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
        vol_label.setStyleSheet("color: #d4d4d4;")
        
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

    def setup_video_network(self):
        """Spins up a local server to receive JPEGs from the C++ renderer."""
        self.expected_video_size = 0
        self.video_server = QTcpServer(self)
        self.video_server.listen(QHostAddress.SpecialAddress.LocalHost, 5557)
        self.video_server.newConnection.connect(self.accept_video_connection)

    def accept_video_connection(self):
        self.video_socket = self.video_server.nextPendingConnection()
        self.video_socket.readyRead.connect(self.read_video_frame)
        self.expected_video_size = 0
        self.console_output.appendPlainText("--- Renderer Video Feed Connected ---")

    def read_video_frame(self):
        """Reads the framed TCP stream, decodes the JPEG, and paints it."""
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

                    # Decode and Paint
                    pixmap = QPixmap()
                    if pixmap.loadFromData(jpeg_data):
                        scaled_pixmap = pixmap.scaled(
                            self.preview_label.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        self.preview_label.setPixmap(scaled_pixmap)
                else:
                    break  # Payload is partially here, wait for the rest

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
        
        def safe_disconnect():
            try:
                self.console_output.appendPlainText("--- Disconnected from OSCAR ---")
            except RuntimeError:
                pass
                
        self.oscar_socket.disconnected.connect(safe_disconnect)
        self.oscar_socket.readyRead.connect(self.read_oscar_stdout)

        # Connect to the engine
        self.oscar_socket.connectToHost("localhost", 5555)

        # Wire up the console input box
        self.console_input.returnPressed.connect(self.send_console_command)

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

                # Peek at the next line to catch orphaned closing brackets
                next_line = end_line + 1
                if next_line < self.editor_widget.lines():
                    next_text = self.editor_widget.text(next_line).strip()
                    # If the next line is a closing character (or comma-trailing closure)
                    if next_text in (']', ')', '}', '],', '),', '},', '"""', "'''"):
                        end_line = next_line
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
        data = self.oscar_socket.readAll().data().decode('utf-8')
        self.stdout_buffer += data

        # Process complete lines one by one
        while '\n' in self.stdout_buffer:
            line, self.stdout_buffer = self.stdout_buffer.split('\n', 1)

            # Did the engine send a hidden UI update?
            if line.startswith("__STATE_SYNC__:"):
                json_str = line.replace("__STATE_SYNC__:", "").strip()
                try:
                    state = json.loads(json_str)
                    self.patch_bay_widget.update_patch_bay(
                        state.get('synths', []),
                        state.get('channels', []),
                        state.get('patches', [])
                    )
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
        self.setWindowTitle(title)

    def setup_menu(self):
        self.setup_file_menu()
        self.setup_edit_menu()
        self.setup_oscar_menu()
        self.setup_help_menu()

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
        text = QLabel(
            """
OSCAR IDE

Version 0.1

by Zeloof Designworks, LLC
            """
        )
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_dialog.layout()#.addWidget(text)
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

    def save_oscar_settings(self, renderer_path, engine_path, dialog):
        self.settings.setValue("oscar_render_path", renderer_path)
        self.settings.setValue("oscar_engine_path", engine_path)
        self.oscar_render_path = renderer_path
        self.oscar_engine_path = engine_path
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
        save_button = QPushButton("Save")
        save_button.clicked.connect(lambda: self.save_oscar_settings(renderer_path_edit.text(), engine_path_edit.text(), oscar_settings_dialog))
        layout.addWidget(save_button)
        oscar_settings_dialog.setLayout(layout)
        oscar_settings_dialog.exec()

    def launch_engine(self):
        self.console_output.appendPlainText(f"> Launching Engine: {self.oscar_engine_path}")
        self.engine_process = QProcess(self)
        self.engine_process.startCommand(self.oscar_engine_path)

    def launch_render(self):
        self.console_output.appendPlainText(f"> Launching Renderer: {self.oscar_render_path}")
        self.render_process = QProcess(self)
        self.render_process.startCommand(self.oscar_render_path)

    # --- File Handling Methods ---
    def new_file(self):
        self.editor_widget.clear()
        self.current_filepath = None
        self.update_window_title()

    def open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", "OSCAR Files (*.os);;Python Files (*.py);;All Files (*)"
        )
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.editor_widget.setText(content)
                self.current_filepath = filepath
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
            self, "Save File", "", "OSCAR Files (*.os);;Python Files (*.py);;All Files (*)"
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

    def query_synth_volume(self, synth_name):
        cmd = f"print(f'__VOL__:{synth_name}:{{{synth_name}.amp()}}')"
        if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
            self.oscar_socket.write((cmd + '\n').encode('utf-8'))

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
        self.console_output.setStyleSheet("font-family: Consolas, monospace;")

        self.console_input = QLineEdit()
        self.console_input.setPlaceholderText("Enter command...")
        self.console_input.setStyleSheet("font-family: Consolas, monospace; padding: 5px;")

        console_layout.addWidget(self.console_output)
        console_layout.addWidget(self.console_input)
        self.console_dock.setWidget(console_widget)

        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.console_dock)

        # --- Preview & Patch Bay Docks ---
        self.preview_dock = QDockWidget("Preview", self)
        self.preview_dock.setObjectName("PreviewDock")
        self.preview_label = QLabel("Waiting for render feed...", alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: black; color: #555;")
        self.preview_dock.setWidget(self.preview_label)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.preview_dock)

        self.patch_dock = QDockWidget("Patch Bay", self)
        self.patch_dock.setObjectName("PatchBayDock")

        self.patch_bay_widget = PatchBayView()
        self.patch_bay_widget.set_callbacks(self.create_interactive_patch, self.delete_interactive_patch, self.show_synth_context_menu, self.query_synth_volume)
        self.patch_dock.setWidget(self.patch_bay_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.patch_dock)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    font = app.font()
    font.setPointSize(12)
    app.setFont(font)

    app.setStyleSheet("""
        QMainWindow, QDockWidget { background-color: #202020; color: white; }
        QPlainTextEdit, QLineEdit { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #333; }
        QsciScintilla { border: none; }
        QMenuBar { background-color: #333; color: white; }
        QMenuBar::item:selected { background-color: #555; }
        QDockWidget::title { background: #2d2d2d; padding: 6px; }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())