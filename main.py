# main.py
import tkinter as tk
from Menu import MenuApp  # Tu clase de menú

def main():
    root = tk.Tk()
    app = MenuApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

