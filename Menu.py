import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from PIL import Image, ImageTk
from registro import RegistroApp
from tree import FamTreeApp

# Pygame para música (opcional)
try:
    import pygame
    PYGAME_OK = True
except ImportError:
    PYGAME_OK = False

# ------------------ UTILIDADES DE COLOR ------------------
def hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in rgb)

def lerp_color(start_hex, end_hex, t):
    start = hex_to_rgb(start_hex)
    end = hex_to_rgb(end_hex)
    interpolated = tuple(start[i] + (end[i] - start[i]) * t for i in range(3))
    return rgb_to_hex(interpolated)

# ------------------ BOTÓN ANIMADO ------------------
class AnimatedButton:
    def __init__(self, canvas, x, y, text, command, font,
                base="#DEB887", hover="#EBC69A", active="#D2B48C", fg="#654321"):
        self.canvas = canvas
        self.x, self.y = x, y
        self.base, self.hover, self.active = base, hover, active
        self.current_bg = base
        self.anim_job = None
        self.is_hover = False
        self.is_pressed = False
        self.command = command

        self.button = tk.Button(
            canvas, text=text, bg=self.base, fg=fg,
            font=font, relief="raised", bd=3,
            activebackground=self.active, activeforeground="#3e2723",
            cursor="hand2", width=16, height=1, highlightthickness=0
        )
        self.win = canvas.create_window(x, y, window=self.button, anchor="n")

        # Eventos
        self.button.bind("<Enter>", self._on_enter)
        self.button.bind("<Leave>", self._on_leave)
        self.button.bind("<ButtonPress-1>", self._on_press)
        self.button.bind("<ButtonRelease-1>", self._on_release)

    def _animate_bg(self, target_hex, duration_ms=140, steps=8):
        if self.anim_job:
            self.canvas.after_cancel(self.anim_job)
            self.anim_job = None

        start = self.current_bg
        step = 0

        def tick():
            nonlocal step
            step += 1
            t = step / steps
            self.current_bg = lerp_color(start, target_hex, t)
            try:
                self.button.configure(bg=self.current_bg)
            except tk.TclError:
                return
            if step < steps:
                self.anim_job = self.canvas.after(max(1, duration_ms // steps), tick)
            else:
                self.current_bg = target_hex
                self.anim_job = None

        tick()

    def _on_enter(self, _):
        self.is_hover = True
        self._animate_bg(self.hover, duration_ms=140, steps=8)
        self.button.configure(highlightthickness=2, highlightbackground="#8d6e63")

    def _on_leave(self, _):
        self.is_hover = False
        self._animate_bg(self.base, duration_ms=160, steps=10)
        self.button.configure(highlightthickness=0)

    def _on_press(self, _):
        self.is_pressed = True
        self._animate_bg(self.active, duration_ms=80, steps=5)
        self.button.configure(relief="sunken")
        self.canvas.move(self.win, 0, 2)

    def _on_release(self, event):
        if not self.is_pressed:
            return
        self.is_pressed = False
        self.button.configure(relief="raised")
        self.canvas.move(self.win, 0, -2)

        target = self.hover if self.is_hover else self.base
        self._animate_bg(target, duration_ms=120, steps=8)

        x, y = event.x, event.y
        if 0 <= x <= self.button.winfo_width() and 0 <= y <= self.button.winfo_height():
            if callable(self.command):
                self.command()

# ------------------ CENTRAR VENTANA ------------------
def center_window(window, width, height):
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")

# ------------------ APP PRINCIPAL ------------------
class MenuApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Family Tree - Menu")
        self.W, self.H = 800, 700
        center_window(root, self.W, self.H)
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(root, width=self.W, height=self.H, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        # Rutas de recursos
        base_dir = Path(__file__).resolve().parent
        self.bg_path = base_dir / "Assets" / "menu" / "Menu.fondo.png"
        self.logo_path = base_dir / "Assets" / "menu" / "logo.png"
        self.music_path = base_dir / "Assets" / "sonidos" / "Menu.music.mp3"
        self.font_path = base_dir / "Assets" / "fonts" / "FrederickatheGreat-Regular.ttf"

        # Inicialización
        self.ui_font = self._load_custom_font()
        self._load_images()
        self._draw_background()
        self._draw_logo()
        self._draw_buttons()
        self._play_music()

        # Cierre limpio
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_custom_font(self):
        family_name = "Fredericka the Great"
        if self.font_path.exists() and sys.platform.startswith("win"):
            try:
                import ctypes
                ctypes.windll.gdi32.AddFontResourceExW(str(self.font_path), 0x10, 0)
            except Exception:
                pass

        try:
            return tkfont.Font(family=family_name, size=14, weight="bold")
        except tk.TclError:
            return tkfont.Font(family="Georgia", size=12, weight="bold")

    def _load_images(self):
        # Fondo con transparencia reducida
        try:
            bg_img = Image.open(self.bg_path).convert("RGBA").resize((self.W, self.H), Image.Resampling.LANCZOS)
            alpha = bg_img.split()[3]
            alpha_reducido = Image.eval(alpha, lambda x: int(x * 0.6))
            bg_img.putalpha(alpha_reducido)
            self.bg_tk = ImageTk.PhotoImage(bg_img)
        except Exception as e:
            raise FileNotFoundError(f"No se pudo abrir la imagen de fondo: {e}")

        # Logo escalado
        try:
            logo_img = Image.open(self.logo_path).convert("RGBA")
            max_w, max_h = 600, 150
            w, h = logo_img.size
            scale = min(max_w / w, max_h / h, 1.0)
            new_size = (int(w * scale), int(h * scale))
            logo_resized = logo_img.resize(new_size, Image.Resampling.LANCZOS)
            self.logo_tk = ImageTk.PhotoImage(logo_resized)
        except Exception as e:
            raise FileNotFoundError(f"No se pudo abrir el logo: {e}")

    def _draw_background(self):
        self.canvas.create_image(0, 0, image=self.bg_tk, anchor="nw")

    def _draw_logo(self):
        self.canvas.create_image(self.W // 2, 20, image=self.logo_tk, anchor="n")

    def _draw_buttons(self):
        def go_register():
            RegistroApp(self.root)  # root es la ventana principal del menú
        def go_fam_tree():
            FamTreeApp(self.root)

        def go_queries(): print("Ir a: Queries")
        def go_exit(): self._on_close()

        buttons = [
            ("REGISTER", go_register),
            ("FAM TREE", go_fam_tree),
            ("QUERIES", go_queries),
            ("EXIT", go_exit),
        ]

        start_y = 260
        gap = 60
        self.animated_buttons = []
        for i, (text, cmd) in enumerate(buttons):
            btn = AnimatedButton(
                canvas=self.canvas,
                x=self.W // 2,
                y=start_y + i * gap,
                text=text,
                command=cmd,
                font=self.ui_font,
                base="#DEB887",
                hover="#EBC69A",
                active="#D2B48C",
                fg="#654321"
            )
            self.animated_buttons.append(btn)

    def _play_music(self):
        if not PYGAME_OK:
            print("pygame no está disponible. La música no se reproducirá.")
            return
        try:
            pygame.mixer.init()
            if self.music_path.exists():
                pygame.mixer.music.load(str(self.music_path))
                pygame.mixer.music.set_volume(0.5)
                pygame.mixer.music.play(-1)
            else:
                print(f"No se encontró la música en {self.music_path}")
        except Exception as e:
            print(f"No se pudo reproducir la música: {e}")

    def _stop_music(self):
        try:
            if PYGAME_OK and pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception:
            pass

    def _on_close(self):
        self._stop_music()
        self.root.destroy()
