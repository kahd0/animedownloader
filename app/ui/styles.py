from tkinter import ttk

def apply_styles(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    
    # Treeview Styles
    style.configure("Treeview", 
                    background="#2a2a2a", 
                    foreground="#ffffff",
                    fieldbackground="#2a2a2a", 
                    rowheight=24, 
                    font=("Segoe UI", 10))
    style.configure("Treeview.Heading", 
                    background="#333333", 
                    foreground="#ffffff",
                    font=("Segoe UI", 10, "bold"))
    style.map("Treeview", background=[("selected", "#1565c0")])
    
    # Entry Styles
    style.configure("TEntry", 
                    fieldbackground="#2a2a2a", 
                    foreground="#ffffff",
                    insertcolor="#ffffff")
    
    # Button Styles
    style.configure("TButton", 
                    background="#333333", 
                    foreground="#ffffff",
                    font=("Segoe UI", 10), 
                    padding=6)
    style.map("TButton", background=[("active", "#444444")])
    
    # Scrollbar Styles
    style.configure("TScrollbar", 
                    background="#333333", 
                    troughcolor="#1e1e1e",
                    arrowcolor="#ffffff")

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
