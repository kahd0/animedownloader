from tkinter import ttk

def apply_styles(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    
    # Modern Dark Mode Palette
    bg_surface = "#1e1e1e"
    bg_dark = "#121212"
    text_color = "#ffffff"
    primary_color = "#bb86fc" # Modern accent color
    secondary_color = "#333333"

    # Treeview Styles
    style.configure("Treeview", 
                    background=bg_surface, 
                    foreground=text_color,
                    fieldbackground=bg_surface, 
                    rowheight=28, # Increased for better click targets
                    borderwidth=0,
                    font=("Segoe UI", 10))
    style.configure("Treeview.Heading", 
                    background=bg_dark, 
                    foreground=text_color,
                    font=("Segoe UI", 10, "bold"),
                    borderwidth=0,
                    padding=6)
    style.map("Treeview", 
              background=[("selected", primary_color)], 
              foreground=[("selected", bg_dark)])
    
    # Entry Styles
    style.configure("TEntry", 
                    fieldbackground=bg_surface, 
                    foreground=text_color,
                    insertcolor=text_color,
                    padding=6)
    
    # Button Styles
    style.configure("TButton", 
                    background=bg_surface, 
                    foreground=text_color,
                    font=("Segoe UI", 10), 
                    padding=6,
                    borderwidth=0)
    style.map("TButton", 
              background=[("active", secondary_color)])
    
    # Scrollbar Styles
    style.configure("TScrollbar", 
                    background=bg_surface, 
                    troughcolor=bg_dark,
                    arrowcolor=text_color,
                    borderwidth=0)

def get_log_tags_colors():
    return {
        "green": "#4caf50", 
        "red": "#f44336", 
        "cyan": "#00bcd4",
        "yellow": "#ffeb3b", 
        "blue": "#2196f3", 
        "orange": "#ff9800", 
        "white": "#ffffff",
    }
