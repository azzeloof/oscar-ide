import os
import json
import re
from PyQt6.Qsci import QsciLexerCustom
from PyQt6.QtGui import QColor, QFont

class OscarLexer(QsciLexerCustom):
    # Style IDs
    DEFAULT = 0
    KEYWORD = 1
    CLASS = 2
    METHOD = 3
    CONSTANT = 4
    STRING = 5
    NUMBER = 6
    COMMENT = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDefaultColor(QColor("#d4d4d4"))
        self.setDefaultPaper(QColor("#1e1e1e"))
        self.setDefaultFont(QFont("Consolas", 12))
        
        # Define styles
        self.setColor(QColor("#d4d4d4"), self.DEFAULT)
        self.setColor(QColor("#569cd6"), self.KEYWORD)
        self.setColor(QColor("#4EC9B0"), self.CLASS)
        self.setColor(QColor("#dcdcaa"), self.METHOD)
        self.setColor(QColor("#4FC1FF"), self.CONSTANT)
        self.setColor(QColor("#ce9178"), self.STRING)
        self.setColor(QColor("#b5cea8"), self.NUMBER)
        self.setColor(QColor("#6a9955"), self.COMMENT)
        
        # Set fonts if needed
        self.setFont(QFont("Consolas", 12), self.DEFAULT)
        
        # Load API definition
        self.api_data = {"python_keywords": [], "oscar_classes": [], "oscar_methods": [], "oscar_constants": []}
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'oscar_api.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self.api_data = json.load(f)

        # Build regex patterns
        # Word boundaries for keywords
        kw_pattern = r'\b(?:' + '|'.join(self.api_data.get("python_keywords", [])) + r')\b' if self.api_data.get("python_keywords") else r'(?!)'
        class_pattern = r'\b(?:' + '|'.join(self.api_data.get("oscar_classes", [])) + r')\b' if self.api_data.get("oscar_classes") else r'(?!)'
        method_pattern = r'\b(?:' + '|'.join(self.api_data.get("oscar_methods", [])) + r')\b' if self.api_data.get("oscar_methods") else r'(?!)'
        const_pattern = r'\b(?:' + '|'.join(self.api_data.get("oscar_constants", [])) + r')\b' if self.api_data.get("oscar_constants") else r'(?!)'
        
        # Strings: single or double quotes
        str_pattern = r'(".*?"|\'.*?\')'
        # Numbers
        num_pattern = r'\b\d+(\.\d+)?\b'
        # Comments
        comment_pattern = r'#.*'

        # Combine into one regex to rule them all, and in the dark mode bind them
        # Use named groups
        self.regex = re.compile(
            f'(?P<COMMENT>{comment_pattern})|'
            f'(?P<STRING>{str_pattern})|'
            f'(?P<KEYWORD>{kw_pattern})|'
            f'(?P<CLASS>{class_pattern})|'
            f'(?P<METHOD>{method_pattern})|'
            f'(?P<CONSTANT>{const_pattern})|'
            f'(?P<NUMBER>{num_pattern})'
        )

    def description(self, style_id):
        descriptions = {
            self.DEFAULT: "Default",
            self.KEYWORD: "Keyword",
            self.CLASS: "Class",
            self.METHOD: "Method",
            self.CONSTANT: "Constant",
            self.STRING: "String",
            self.NUMBER: "Number",
            self.COMMENT: "Comment",
        }
        return descriptions.get(style_id, "")

    def styleText(self, start, end):
        self.startStyling(start)
        editor = self.editor()
        if not editor:
            return
            
        text = editor.text()[start:end]
        
        # Reset all text to default style first
        self.setStyling(len(text), self.DEFAULT)
        
        # Apply specific styles using regex matches
        for match in self.regex.finditer(text):
            for group_name, group_value in match.groupdict().items():
                if group_value:
                    style = getattr(self, group_name, self.DEFAULT)
                    
                    # Calculate styling position and length
                    # Text bytes vs string length might differ if non-ascii, but QScintilla expects byte-like length.
                    # QsciLexerCustom handles utf-8 natively in python strings, but we must use byte length of string.
                    # A safer way: match.start() is in character indices.
                    # SendScintilla requires byte positions, but QsciLexerCustom's setStyling operates on characters when called from PyQt.
                    
                    # NOTE: PyQt6 QsciLexerCustom expects byte length for styling.
                    # If we have utf-8, `len(group_value)` is char length. 
                    # We can use `.encode('utf-8')` to get byte lengths.
                    
                    prefix_bytes = len(text[:match.start(group_name)].encode('utf-8'))
                    match_bytes = len(group_value.encode('utf-8'))
                    
                    self.startStyling(start + prefix_bytes)
                    self.setStyling(match_bytes, style)
