import dearpygui.dearpygui as dpg

dpg.create_context()

editor_state = {
    "text": "# your code here\n"
}

def text_editor_callback(sender, app_data, user_data):
    new_text = app_data
    old_text = editor_state["text"]
    
    # -- Auto-indent Logic --
    # If text was added, see if a newline was just inserted
    if len(new_text) > len(old_text):
        diff_len = len(new_text) - len(old_text)
        diff_idx = 0
        while diff_idx < min(len(old_text), len(new_text)) and old_text[diff_idx] == new_text[diff_idx]:
            diff_idx += 1
            
        added_char = new_text[diff_idx:diff_idx+diff_len]
        if added_char in ('\n', '\r\n'):
            # Find the line that was just 'Enter'ed from
            prev_newline = old_text.rfind('\n', 0, diff_idx)
            prev_line = old_text[prev_newline+1:diff_idx] if prev_newline != -1 else old_text[:diff_idx]
            
            # Count leading spaces/tabs
            spaces_count = len(prev_line) - len(prev_line.lstrip(' \t'))
            indent = prev_line[:spaces_count]
            
            # Python auto-tab: increase indent if line ends with a colon
            if prev_line.strip().endswith(':'):
                indent += "    "
                
            if len(indent) > 0:
                # Inject the same/increased indentation right after the new newline
                new_text = new_text[:diff_idx+len(added_char)] + indent + new_text[diff_idx+len(added_char):]
                dpg.set_value(sender, new_text)

    n_lines = new_text.count("\n") + 1
    line_nums = "\n".join(str(i) for i in range(1, n_lines + 1))
    dpg.set_value("line_numbers", line_nums)
    
    # Prevent internal scrolling by expanding the item height. 
    # With global_font_scale=2.0, each line is ~26 pixels.
    content_height = max(800, int(n_lines * 27 + 50))
    dpg.set_item_height("line_numbers", content_height)
    dpg.set_item_height("editor_input", content_height)
    
    # -- Auto-scroll Logic --
    # Find the cursor location by diffing old and new text
    diff_index = 0
    min_len = min(len(old_text), len(new_text))
    while diff_index < min_len and old_text[diff_index] == new_text[diff_index]:
        diff_index += 1
        
    current_line = new_text.count("\n", 0, diff_index)
    
    try:
        scroll_y = dpg.get_y_scroll("editor_scroll_window")
        window_height = dpg.get_item_rect_size("editor_scroll_window")[1]
        
        # Calculate approximate Y position of the cursor (27px per line + top padding)
        cursor_y = current_line * 27 + 8
        
        # Scroll down if cursor is below visible area
        if cursor_y > scroll_y + window_height - 35:
            dpg.set_y_scroll("editor_scroll_window", cursor_y - window_height + 35)
        # Scroll up if cursor is above visible area
        elif cursor_y < scroll_y:
            dpg.set_y_scroll("editor_scroll_window", cursor_y)
    except SystemError:
        pass # window not yet rendered
        
    editor_state["text"] = new_text

# --- Primary window: just the menu bar ---
with dpg.window(tag="Primary Window"):
    pass

with dpg.viewport_menu_bar():
    with dpg.menu(label="File"):
        dpg.add_menu_item(label="Quit", callback=lambda: dpg.stop_dearpygui())
        dpg.add_menu_item(
            label="Save Layout",
            callback=lambda: dpg.save_init_file("dpg.ini"),
        )
    with dpg.menu(label="View"):
        pass

# --- Editor window (separate, will dock into center) ---
with dpg.window(label="Editor", tag="editor_window"):
    with dpg.child_window(tag="editor_scroll_window", width=-1, height=-1):
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                multiline=True,
                width=50,
                height=800,
                readonly=True,
                tag="line_numbers",
                default_value="1\n2"
            )
            dpg.add_input_text(
                multiline=True,
                width=-1,
                height=800,
                tab_input=True,
                tag="editor_input",
                default_value="# your code here\n",
                callback=text_editor_callback,
            )

# --- Console window (separate, will dock to bottom) ---
with dpg.window(label="Console", tag="console_window"):
    dpg.add_input_text(
        multiline=True,
        readonly=True,
        width=-1,
        height=-35,
        default_value="> ready.\n",
        tag="console_output",
    )
    dpg.add_input_text(hint="Enter command...", width=-1)


with dpg.window(label="Preview", tag="preview_window"):
    dpg.add_text("Preview")


with dpg.window(label="Patch Bay", tag="patchbay_window"):
    dpg.add_text("Patch Bay")

# --- App config: enable docking to the viewport ---
dpg.configure_app(docking=True, docking_space=True, init_file="dpg.ini")

dpg.create_viewport(title="OSCAR", width=1600, height=1000)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.set_global_font_scale(2.0)
dpg.set_primary_window("Primary Window", True)
dpg.start_dearpygui()
dpg.destroy_context()