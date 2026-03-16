import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QDockWidget, QLineEdit, QPlainTextEdit,
                             QLabel, QFileDialog, QMessageBox)
from PyQt6.QtGui import QAction, QColor, QFont, QShortcut, QKeySequence, QPixmap
from PyQt6.QtCore import Qt, QSettings, QTimer
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
        self.setup_network()
        self.setup_shortcuts()
        self.setup_video_network()

        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.check_engine_connection)
        self.reconnect_timer.start(2000)  # Check every 2 seconds

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
        self.oscar_socket.disconnected.connect(
            lambda: self.console_output.appendPlainText("--- Disconnected from OSCAR ---"))
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

            # Find the very last child of this root block
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

        # Beam it to the engine
        if self.oscar_socket.state() == QTcpSocket.SocketState.ConnectedState:
            payload = code_to_run + '\n'
            self.oscar_socket.write(payload.encode('utf-8'))
        else:
            self.console_output.appendPlainText("! Not connected to OSCAR. Retrying connection...")
            self.oscar_socket.connectToHost("localhost", 5555)

    def read_oscar_stdout(self):
        """Receives live prints/errors from the OSCAR engine."""
        data = self.oscar_socket.readAll().data().decode('utf-8')

        cursor = self.console_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(data)
        self.console_output.ensureCursorVisible()

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

    def setup_oscar_menu(self):
        oscar_menu = self.menuBar().addMenu("OSCAR")

        launch_engine_action = QAction("Launch Engine", self)
        launch_engine_action.triggered.connect(self.launch_engine)
        oscar_menu.addAction(launch_engine_action)

        launch_render_action = QAction("Launch Render", self)
        launch_render_action.triggered.connect(self.launch_render)
        oscar_menu.addAction(launch_render_action)

    def launch_engine(self):
        pass

    def launch_render(self):
        os.system("oscar_render &")

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
        self.patch_dock.setWidget(QLabel("Patch Bay Area", alignment=Qt.AlignmentFlag.AlignCenter))
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