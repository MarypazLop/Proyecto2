# tree.py
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageDraw
from kinship import Kinship
import queue
from birthday import BirthdayEngine 
from fallecimientos import DeathEngine
from nacimientos import BirthEngine
from uniones import UnionsEngine
from emocional import EmotionalHealthEngine
from panel import EventPanel

# --- Rutas absolutas ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAMILIAS_FILE = os.path.join(BASE_DIR, "familias.txt")
PERSONAS_FILE = os.path.join(BASE_DIR, "personas.txt")
AVATAR_DIR = os.path.join(BASE_DIR, "Assets", "personas")

# Autodetectar fondo en varios formatos
def _detect_bg_path():
    carpeta = os.path.join(BASE_DIR, "Assets", "fondo")
    for name in ("fondo", "background", "bg"):
        for ext in (".png", ".jpg", ".jpeg"):
            p = os.path.join(carpeta, name + ext)
            if os.path.exists(p):
                return p
    return None

BG_PATH = _detect_bg_path()  # puede ser None

# ---- Ajustes visuales básicos ----
NODE_W, NODE_H = 120, 140
AVATAR = 80
H_GAP, V_GAP = 70, 160
MARGIN_X, MARGIN_Y = 70, 70
COUPLE_GAP = 16
LEVEL_LINE_COLOR = "#e7dcc7"
LEVEL_LINE_WIDTH = 1

# Colores
COL_CANVAS = "#fffaf0"
COL_NODE_FILL = "#fff3d8"
COL_NODE_BORDER = "#8d6e63"
COL_NODE_TEXT = "#4a342f"
COL_LINE_PARENT = "#0066ff"   # Azul para padres-hijos
COL_LINE_SPOUSE = "#ff0000"   # Rojo para parejas
COL_LINE_SIBLING = "#ffd700"  # Amarillo para hermanos

# ---- Utilidad: rectángulo redondeado en Canvas ----
def create_round_rect(canvas, x0, y0, x1, y1, r=14, **kwargs):
    r = max(0, min(r, (x1 - x0) // 2, (y1 - y0) // 2))
    items = []
    items.append(canvas.create_arc(x0, y0, x0+2*r, y0+2*r, start=90, extent=90, style="pieslice", **kwargs))
    items.append(canvas.create_arc(x1-2*r, y0, x1, y0+2*r, start=0, extent=90, style="pieslice", **kwargs))
    items.append(canvas.create_arc(x0, y1-2*r, x0+2*r, y1, start=180, extent=90, style="pieslice", **kwargs))
    items.append(canvas.create_arc(x1-2*r, y1-2*r, x1, y1, start=270, extent=90, style="pieslice", **kwargs))
    items.append(canvas.create_rectangle(x0+r, y0, x1-r, y1, **kwargs))
    items.append(canvas.create_rectangle(x0, y0+r, x1, y1-r, **kwargs))
    return items

class Tooltip:
    def __init__(self, widget):
        self.widget = widget
        self.tip = None

    def show(self, text, x, y):
        self.hide()
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        label = tk.Label(
            self.tip, text=text, justify="left",
            bg="#333", fg="#fff", padx=8, pady=4,
            font=("Segoe UI", 9)
        )
        label.pack()
        self.tip.geometry(f"+{x+16}+{y+16}")

    def hide(self):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None

class FamTreeApp(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Family Tree - Visualizador")
        self.geometry("1120x760")
        self.minsize(920, 600)
        self.configure(bg="#f5f5dc")

        self.zoom_scale = 1.0
        self.tooltip = Tooltip(self)

        # Contenedor
        self.container = tk.Frame(self, bg="#f5f5dc")
        self.container.pack(fill="both", expand=True)

        # Topbar
        self.topbar = tk.Frame(self.container, bg="#f5f5dc")
        self.topbar.pack(fill="x", padx=10, pady=8)

        # Canvas + scrollbars
        self.canvas_frame = tk.Frame(self.container, bg="#f5f5dc")
        self.canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg=COL_CANVAS, highlightthickness=0)
        self.hbar = tk.Scrollbar(self.canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.vbar = tk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")

        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)

        # Datos
        self.familias = self._load_familias()
        self.personas = self._load_personas()
        self.avatar_cache = {}
        self.bg_cache = None  # (w,h) -> tkimage
        self.spouse_of = self._build_spouse_index()
        self.kin = Kinship(self.personas)

        self.node_hitmap = {}  # canvas_id -> cedula (para tooltips)

        # Para fondo responsive
        self._content_w = 0
        self._content_h = 0
        self._bg_drawn_size = (0, 0)

        # UI
        tk.Label(self.topbar, text="Familia:", bg="#f5f5dc").pack(side="left")
        self.sel_familia = tk.StringVar()
        self.combo_familia = ttk.Combobox(
            self.topbar, textvariable=self.sel_familia, state="readonly",
            values=[f"{fid} - {name}" for fid, name in self.familias]
        )
        self.combo_familia.pack(side="left", padx=6)
        self.combo_familia.bind("<<ComboboxSelected>>", self._redraw)

        tk.Button(self.topbar, text="Redibujar", command=self._redraw).pack(side="left", padx=6)
        tk.Button(self.topbar, text="Centrar", command=self._center_view).pack(side="left", padx=6)
        tk.Button(self.topbar, text="Exportar PNG", command=self._export_png).pack(side="left", padx=6)

        # Eventos
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom)          # Windows
        self.canvas.bind("<Control-Button-4>", self._on_zoom_linux_up)   # Linux up
        self.canvas.bind("<Control-Button-5>", self._on_zoom_linux_down) # Linux down

        # Tooltips
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda e: self.tooltip.hide())

        if self.familias:
            self.sel_familia.set(f"{self.familias[0][0]} - {self.familias[0][1]}")
            self._redraw()
            
        # ---- Controles de simulación ----
        self.var_show_cumples = tk.BooleanVar(value=False)

        self.btn_start = tk.Button(self.topbar, text="Iniciar sim", command=self._start_sim)
        self.btn_stop  = tk.Button(self.topbar, text="Detener", command=self._stop_sim, state="disabled")
        tk.Button(self.topbar, text="Panel eventos", command=self._open_event_panel).pack(side="left", padx=6)
        self._event_panel = None

        self.lbl_timer = tk.Label(self.topbar, text="Año sim: —  | Próximo tick: —s", bg="#f5f5dc")

        self.btn_start.pack(side="left", padx=6)
        self.btn_stop.pack(side="left", padx=6)
        self.lbl_timer.pack(side="left", padx=16)

        # ---- Motores + cola de eventos (NO los inicies aquí) ----
        self._evt_queue = queue.Queue()
        self._sim_running = False

        # Conecta BirthdayEngine (1 año por 10s)
        self.birthday = BirthdayEngine(
            self.personas,
            segundos_por_tick=10,
            on_change=self._on_sim_change,
            on_event=self._on_sim_event
        )

        self.deaths = DeathEngine(
            self.personas,
            segundos_por_tick=10,
            on_change=self._on_sim_change,
            on_event=self._on_sim_event,
            get_anio_sim=lambda: self.birthday.anio_sim,  # mismo año sim
            hard_max_age=100,     # nadie cumple 100
            risk_age_floor=80,    # alta prob a partir de 80
            max_gap_years=2       # garantía: 1 muerte cada 2 años
        )
        
        self.births = BirthEngine(
            self.personas,
            self.familias,
            segundos_por_tick=10,
            on_change=self._on_sim_change,
            on_event=self._on_sim_event,
            get_anio_sim=lambda: self.birthday.anio_sim,
            min_compatibilidad_nacimiento=0.30,  # 30%
            max_anios_sin_nacer=2,               # garantía
            prob_nacimiento_por_pareja=0.20
        )

        self.unions = UnionsEngine(
            self.personas,
            self.familias,
            segundos_por_tick=10,
            on_change=self._on_sim_change,
            on_event=self._on_sim_event,
            get_anio_sim=lambda: self.birthday.anio_sim,  # sincroniza con cumpleaños
            umbral_compat=0.20,
            prob_union_por_par=0.8,
            max_uniones_por_anio=5,
            personas_file=PERSONAS_FILE
        )

        self.emotions = EmotionalHealthEngine(
            personas=self.personas,
            segundos_por_tick=10,
            on_change=self._on_sim_change,
            on_event=self._on_sim_event,
            get_anio_sim=lambda: self.birthday.anio_sim,
            years_threshold=5,
            base_decay=8,
            accel_decay=2,
            mortality_threshold=5
        )

        self._countdown = self.birthday.segundos_por_tick
        self._update_timer_ui()   # pinta el estado inicial
    
    def _open_event_panel(self):
    # Crea o muestra el panel
        if self._event_panel is None or not self._event_panel.winfo_exists():
            self._event_panel = EventPanel(self, show_birthdays=False, auto_scroll=True)
        else:
            self._event_panel.deiconify()
            self._event_panel.lift()

    # --- cierre limpio de la ventana ---
    def destroy(self):
        try:
            if getattr(self, "_sim_running", False):
                self._stop_sim()  # detiene birthday/births/deaths si los tienes conectados ahí
        finally:
            super().destroy()

    # --------- Carga de datos ----------
    def _load_familias(self):
        out = []
        if os.path.exists(FAMILIAS_FILE):
            with open(FAMILIAS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    partes = line.split(";")
                    if len(partes) >= 2:
                        out.append((partes[0].strip(), partes[1].strip()))
        return out

    def _load_personas(self):
        p = {}
        if os.path.exists(PERSONAS_FILE):
            with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = line.split(";")
                    if len(d) < 13:
                        continue
                    fam_id = d[0].split(" - ")[0].strip()
                    p[d[1].strip()] = {
                        "familia": fam_id,
                        "cedula": d[1].strip(),
                        "nombre": d[2].strip(),
                        "nac": d[3].strip(),
                        "falle": d[4].strip(),
                        "genero": d[5].strip(),
                        "provincia": d[6].strip(),
                        "estado": d[7].strip(),
                        "avatar": d[8].strip(),
                        "padre": d[9].strip(),
                        "madre": d[10].strip(),
                        "pareja": d[11].strip(),
                        "filiacion": d[12].strip()
                    }
        return p

    def _id_from_combo(self, text):
        if not text:
            return ""
        return text.split(" - ")[0].strip()

    def _build_spouse_index(self):
        spouse = {}
        for c in self.personas.values():
            if c.get("estado") in ("Casado/a", "Unión libre"):
                m = self._id_from_combo(c.get("pareja", ""))
                if m and m in self.personas:
                    spouse[c["cedula"]] = m
        return spouse

    # --------- Cálculo de layout ----------
    def _compute_generations(self, cedulas_fam):
        # 1) Inicializa niveles por ascendencia (padres -> hijo = +1)
        level = {c: 0 for c in cedulas_fam}
        changed = True
        loops = 0
        while changed and loops < 60:
            changed = False
            loops += 1
            for ced in cedulas_fam:
                p = self.personas[ced]
                parents = []
                for par in (self._id_from_combo(p.get("padre")), self._id_from_combo(p.get("madre"))):
                    if par in level:
                        parents.append(level[par])
                if parents:
                    new = max(parents) + 1
                    if new != level[ced]:
                        level[ced] = new
                        changed = True

        # 2) Igualar cónyuges al mismo nivel (al MÁXIMO entre ambos)
        spouse_changed = True
        loops = 0
        while spouse_changed and loops < 60:
            spouse_changed = False
            loops += 1
            for a, pa in self.personas.items():
                b = self.spouse_of.get(a)
                if not b or b not in level:
                    continue
                la, lb = level[a], level[b]
                target = max(la, lb)
                if la != target:
                    level[a] = target
                    spouse_changed = True
                if lb != target:
                    level[b] = target
                    spouse_changed = True

            # Re-afirmar la restricción de padres->hijo (+1) si algo se movió
            if spouse_changed:
                for ced in cedulas_fam:
                    p = self.personas[ced]
                    parents = []
                    for par in (self._id_from_combo(p.get("padre")), self._id_from_combo(p.get("madre"))):
                        if par in level:
                            parents.append(level[par])
                    if parents:
                        min_child = max(parents) + 1
                        if level[ced] < min_child:
                            level[ced] = min_child
                            spouse_changed = True

        return level

    def _group_couples_in_level(self, row):
        seen = set()
        blocks = []
        for ced in row:
            if ced in seen:
                continue
            mate = self.spouse_of.get(ced, "")
            if mate and mate in row and mate not in seen:
                a, b = (ced, mate) if ced < mate else (mate, ced)
                blocks.append([a, b])
                seen.add(a); seen.add(b)
            else:
                blocks.append([ced])
                seen.add(ced)

        def key_name(block):
            n = self.personas[block[0]]["nombre"].lower()
            return n

        blocks.sort(key=key_name)
        return blocks

    def _compute_positions(self, levels, cedulas_fam):
        by_level = {}
        max_level = max(levels.values()) if levels else 0
        for ced in cedulas_fam:
            by_level.setdefault(levels[ced], []).append(ced)
        for lvl in by_level:
            by_level[lvl].sort(key=lambda c: self.personas[c]["nombre"].lower())

        level_blocks = {lvl: self._group_couples_in_level(by_level[lvl]) for lvl in by_level}

        def block_width(block):
            if len(block) == 1:
                return NODE_W
            return NODE_W*len(block) + COUPLE_GAP*(len(block)-1)

        max_blocks = max((len(level_blocks[lvl]) for lvl in level_blocks), default=1)
        content_w = max_blocks * (max(NODE_W, 120) + H_GAP) + MARGIN_X*2
        content_h = (max_level + 1) * (NODE_H + V_GAP) + MARGIN_Y*2

        positions = {}
        for lvl in range(max_level + 1):
            blocks = level_blocks.get(lvl, [])
            x = MARGIN_X
            y = MARGIN_Y + lvl*(NODE_H + V_GAP) + NODE_H//2
            for block in blocks:
                w = block_width(block)
                cx = x + w//2
                if len(block) == 1:
                    positions[block[0]] = (cx, y)
                else:
                    total = NODE_W*len(block) + COUPLE_GAP*(len(block)-1)
                    left_start = cx - total//2 + NODE_W//2
                    for i, ced in enumerate(block):
                        xi = left_start + i*(NODE_W + COUPLE_GAP)
                        positions[ced] = (xi, y)
                x += w + H_GAP
        return positions, content_w, content_h, max_level

    # --------- Dibujo ----------
    def _redraw(self, *_):
        self.tooltip.hide()
        self.canvas.delete("content")  # borra solo el contenido, no el fondo
        self.node_hitmap.clear()

        # 🔁 Recalcular índice de parejas (no usado por cumpleaños, pero útil si ya hay datos)
        self.spouse_of = self._build_spouse_index()

        # 🧭 Familia seleccionada
        familia_id = self._id_from_combo(self.sel_familia.get())

        # 👀 Incluir miembros de familia principal O presentes en familias_extra
        cedulas_fam = [
            ced for ced, p in self.personas.items()
            if p.get("familia", "") == familia_id
            or familia_id in (p.get("familias_extra") or [])
        ]
        # 🚫 Duplicados y orden por nombre
        cedulas_fam = sorted(set(cedulas_fam), key=lambda c: self.personas[c]["nombre"].lower())

        if not cedulas_fam:
            messagebox.showinfo("Sin datos", "Esta familia aún no tiene integrantes registrados.")
            return

        levels = self._compute_generations(cedulas_fam)
        positions, content_w, content_h, max_level = self._compute_positions(levels, cedulas_fam)

        # Aire extra
        content_w = int(content_w * 1.2)
        content_h = int(content_h * 1.2)

        # Fondo/scroll
        self._content_w, self._content_h = content_w, content_h
        self._fit_background()

        # Líneas de nivel (decorativas)
        for lvl in range(max_level + 1):
            y = MARGIN_Y + lvl*(NODE_H + V_GAP) + NODE_H//2
            self.canvas.create_line(
                MARGIN_X//3, y + AVATAR//2 + 6,
                content_w - MARGIN_X//3, y + AVATAR//2 + 6,
                fill=LEVEL_LINE_COLOR, width=LEVEL_LINE_WIDTH, tags=("content",)
            )

        # Enlaces padre/madre -> hijo (AZUL)
        for ced in cedulas_fam:
            p = self.personas[ced]
            padre = self._id_from_combo(p.get("padre"))
            madre = self._id_from_combo(p.get("madre"))
            child_pos = positions.get(ced)
            for par in (padre, madre):
                if par and par in positions and child_pos:
                    self._draw_parent_link(positions[par], child_pos)

        # Enlaces hermanos (AMARILLO)
        self._draw_sibling_links(cedulas_fam, positions)

        # Enlaces conyugales (ROJO)
        drawn = set()
        for ced in cedulas_fam:
            mate = self.spouse_of.get(ced, "")
            if mate and mate in positions:
                a, b = sorted([ced, mate])
                if (a, b) not in drawn:
                    self._draw_spouse_link(positions[a], positions[b])
                    drawn.add((a, b))

        # Nodos
        for ced in cedulas_fam:
            self._draw_person_node(ced, positions[ced])

        # Scrollregion
        view_w = max(self._content_w, self.canvas.winfo_width())
        view_h = max(self._content_h, self.canvas.winfo_height())
        self.canvas.config(scrollregion=(0, 0, view_w, view_h))
        self._center_view()

    def _center_view(self):
        self.update_idletasks()
        bbox = self.canvas.bbox("content")
        if not bbox:
            return
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    # ---- Fondo pergamino (cover) ----
    def _draw_background(self, w, h):
        self.canvas.delete("bg")
        if not BG_PATH or not os.path.exists(BG_PATH):
            self.canvas.create_rectangle(0, 0, w, h, fill=COL_CANVAS, outline="", tags=("bg",))
            self.canvas.tag_lower("bg")
            return

        cache_key = (w, h)
        if self.bg_cache and self.bg_cache[0] == cache_key:
            tkimg = self.bg_cache[1]
        else:
            try:
                base = Image.open(BG_PATH).convert("RGB")
                bw, bh = base.size
                scale = max(w / bw, h / bh)
                new_size = (max(1, int(bw * scale)), max(1, int(bh * scale)))
                img = base.resize(new_size, Image.Resampling.LANCZOS)
                x_left = max(0, (img.width - w) // 2)
                y_top = max(0, (img.height - h) // 2)
                img = img.crop((x_left, y_top, x_left + w, y_top + h))
                tkimg = ImageTk.PhotoImage(img)
                self.bg_cache = (cache_key, tkimg)
            except Exception:
                tkimg = None

        if tkimg:
            self.canvas.create_image(0, 0, image=tkimg, anchor="nw", tags=("bg",))
            self.canvas.bg_image_ref = tkimg  # evitar GC
        else:
            self.canvas.create_rectangle(0, 0, w, h, fill=COL_CANVAS, outline="", tags=("bg",))
        self.canvas.tag_lower("bg")

    def _on_canvas_configure(self, event):
        if self._content_w == 0 and self._content_h == 0:
            return
        self._fit_background()
        view_w = max(self._content_w, self.canvas.winfo_width())
        view_h = max(self._content_h, self.canvas.winfo_height())
        self.canvas.config(scrollregion=(0, 0, view_w, view_h))

    def _fit_background(self):
        need_w = max(self._content_w, self.canvas.winfo_width())
        need_h = max(self._content_h, self.canvas.winfo_height())
        if (need_w, need_h) != self._bg_drawn_size:
            self._draw_background(need_w, need_h)
            self._bg_drawn_size = (need_w, need_h)

    # ---- Enlaces ----
    def _draw_parent_link(self, a, b):
        ax, ay = a
        bx, by = b
        mx = (ax + bx) / 2
        o = AVATAR//2 - 6
        self.canvas.create_line(
            ax, ay + o,
            mx, ay + o,
            mx, by - o,
            bx, by - o,
            smooth=True, width=2, fill=COL_LINE_PARENT, tags=("content",)
        )

    def _draw_spouse_link(self, a, b):
        ax, ay = a
        bx, by = b
        y = (ay + by) // 2
        self.canvas.create_line(
            ax + NODE_W//2 - AVATAR//2, y,
            bx - NODE_W//2 + AVATAR//2, y,
            width=3, fill=COL_LINE_SPOUSE, capstyle="round", tags=("content",)
        )

    def _draw_sibling_links(self, cedulas_fam, positions):
        groups = {}
        for ced in cedulas_fam:
            p = self.personas[ced]
            padre = self._id_from_combo(p.get("padre"))
            madre = self._id_from_combo(p.get("madre"))
            if padre or madre:
                key = (padre or "-", madre or "-")
                groups.setdefault(key, []).append(ced)

        for key, hermanos in groups.items():
            if len(hermanos) < 2:
                continue
            hs = [h for h in hermanos if h in positions]
            if len(hs) < 2:
                continue
            hs.sort(key=lambda c: positions[c][0])
            x_left = positions[hs[0]][0]
            x_right = positions[hs[-1]][0]
            y = positions[hs[0]][1] + AVATAR//2 - 2
            self.canvas.create_line(
                x_left, y, x_right, y,
                width=2, fill=COL_LINE_SIBLING, tags=("content",)
            )

    # ---- Nodo persona ----
    def _draw_person_node(self, cedula, center):
        p = self.personas[cedula]
        x, y = center
        x0 = x - NODE_W//2
        y0 = y - NODE_H//2
        x1 = x + NODE_W//2
        y1 = y + NODE_H//2

        # Sombra
        self.canvas.create_rectangle(
            x0+3, y0+4, x1+3, y1+4,
            fill="#000000", outline="", stipple="gray25",
            tags=("content",)
        )

        # Tarjeta redondeada
        border_items = create_round_rect(
            self.canvas, x0, y0, x1, y1, r=14,
            fill=COL_NODE_FILL, outline=COL_NODE_BORDER, width=2
        )
        for it in border_items:
            self.canvas.addtag_withtag("content", it)

        # Avatar
        img = self._get_avatar_image(p.get("avatar"))
        self.canvas.create_image(x, y - 18, image=img, tags=("content",))
        if not hasattr(self, "_imgs"):
            self._imgs = []
        self._imgs.append(img)

        # Texto: nombre (con ✝ si falleció)
        falle = p.get("falle", "")
        falle_icon = " ✝" if falle else ""
        label = p.get("nombre", "") + falle_icon
        self.canvas.create_text(
            x, y + AVATAR//2 - 4,
            text=label, font=("Georgia", 10, "bold"),
            fill=COL_NODE_TEXT, tags=("content",)
        )

        # Área clicable para tooltip
        clickable = self.canvas.create_rectangle(
            x0, y0, x1, y1, outline="", fill="", tags=("content",)
        )
        self.node_hitmap[clickable] = cedula

        # Indicador de adopción (puntito verde)
        if str(self.personas[cedula].get("adoptado","")).strip():
            r = 6
            self.canvas.create_oval(x1-2*r-4, y0+4, x1-4, y0+2*r+4, fill="#1db954", outline="", tags=("content",))

    def _get_avatar_image(self, avatar_name):
        path = os.path.join(AVATAR_DIR, avatar_name or "")
        key = (path, AVATAR)
        if key in self.avatar_cache:
            return self.avatar_cache[key]
        try:
            im = Image.open(path).convert("RGBA").resize((AVATAR, AVATAR), Image.Resampling.LANCZOS)
        except Exception:
            im = Image.new("RGBA", (AVATAR, AVATAR), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            r = AVATAR//2 - 2
            cx = cy = AVATAR//2
            d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(255, 243, 216, 255), outline=(141, 110, 99, 255), width=2)
        tkimg = ImageTk.PhotoImage(im)
        self.avatar_cache[key] = tkimg
        return tkimg

    # --------- Zoom (solo contenido) ----------
    def _on_zoom(self, event):
        if event.delta > 0:
            self._apply_zoom(1.1, event)
        else:
            self._apply_zoom(1/1.1, event)

    def _on_zoom_linux_up(self, event):
        self._apply_zoom(1.1, event)

    def _on_zoom_linux_down(self, event):
        self._apply_zoom(1/1.1, event)

    def _apply_zoom(self, factor, event):
        new_scale = self.zoom_scale * factor
        new_scale = max(0.5, min(2.5, new_scale))
        factor = new_scale / self.zoom_scale
        self.zoom_scale = new_scale

        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        # Escalar solo el contenido
        self.canvas.scale("content", x, y, factor, factor)
        x0, y0, x1, y1 = self.canvas.bbox("content")
        if x0 is not None:
            self.canvas.config(scrollregion=(0, 0, max(self._content_w, x1), max(self._content_h, y1)))

    # --------- Tooltips ----------
    def _on_motion(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(x, y, x, y)
        for it in items[::-1]:
            if it in self.node_hitmap:
                ced = self.node_hitmap[it]
                p = self.personas.get(ced, {})
                txt = self._tooltip_text(p)
                self.tooltip.show(txt, event.x_root, event.y_root)
                return
        self.tooltip.hide()

    def _fmt_names(self, ids):
        lst = [c for c in ids if c]
        if not lst:
            return "-"
        return "; ".join(f"{c} - {self.personas.get(c, {}).get('nombre', c)}" for c in sorted(set(lst)))

    def _tooltip_text(self, p):
        # Info básica
        lines = [
            f"Nombre: {p.get('nombre','')}",
            f"Cédula: {p.get('cedula','')}",
            f"Nacimiento: {p.get('nac','') or '-'}",
        ]
        # Edad (actualizada por BirthdayEngine)
        if p.get("edad"):
            lines.append(f"Edad: {p.get('edad')} años")
        if p.get("falle"):
            lines.append(f"Fallecimiento: {p.get('falle')}")
        if p.get("estado"):
            lines.append(f"Estado civil: {p.get('estado')}")
        if p.get("provincia"):
            lines.append(f"Provincia: {p.get('provincia')}")

        padre = self._id_from_combo(p.get("padre"))
        madre = self._id_from_combo(p.get("madre"))
        if padre:
            lines.append(f"Padre: {self.personas.get(padre,{}).get('nombre','')}")
        if madre:
            lines.append(f"Madre: {self.personas.get(madre,{}).get('nombre','')}")

        # Parentescos (Kinship)
        ced = p.get("cedula", "")
        if hasattr(self, "kin") and ced:
            lines.append("Hijos/as: " + self._fmt_names(self.kin.get_children(ced)))
            sp = self.kin.get_spouse(ced)
            lines.append("Pareja: " + (self._fmt_names([sp]) if sp else "-"))
            lines.append("Hermanos/as (completos): " + self._fmt_names(self.kin.full_siblings(ced)))
            lines.append("Medio hermanos/as: " + self._fmt_names(self.kin.half_siblings(ced)))
            lines.append("Abuelos/as: " + self._fmt_names(self.kin.grandparents(ced)))
            lines.append("Nietos/as: " + self._fmt_names(self.kin.grandchildren(ced)))
            lines.append("Tíos/Tías (políticos incluidos): " + self._fmt_names(self.kin.uncles_aunts(ced, include_inlaws=True)))
            lines.append("Primos/as: " + self._fmt_names(self.kin.cousins(ced)))
            lines.append("Sobrinos/as: " + self._fmt_names(self.kin.nieces_nephews(ced)))

        return "\n".join(lines)

    # --------- Exportar PNG ----------
    def _export_png(self):
        try:
            x0, y0, x1, y1 = self.canvas.bbox("content")
            if not (x0 or y0 or x1 or y1):
                messagebox.showerror("Exportar", "No hay contenido para exportar.")
                return
            w = int(x1 - x0)
            h = int(y1 - y0)

            ps = filedialog.asksaveasfilename(
                title="Guardar como",
                defaultextension=".png",
                filetypes=[("PNG", "*.png")]
            )
            if not ps:
                return

            tmp_eps = ps.replace(".png", ".eps")

            self.canvas.postscript(file=tmp_eps, colormode="color", pagewidth=w-1, pageheight=h-1)
            img = Image.open(tmp_eps)
            img.load()
            img = img.convert("RGBA")
            img.save(ps, "PNG")
            try:
                os.remove(tmp_eps)
            except Exception:
                pass

            messagebox.showinfo("Exportar", f"Imagen exportada en:\n{ps}")
        except Exception as e:
            messagebox.showerror("Exportar", f"No se pudo exportar la imagen.\nDetalle: {e}")

    # --------- Simulación: start / stop (3 motores) ----------
    def _start_sim(self):
        # Evita doble inicio
        if getattr(self, "_sim_running", False):
            return
        try:
            # Arranca motores si existen
            if hasattr(self, "birthday"): self.birthday.start()
            if hasattr(self, "births"):   self.births.start()
            if hasattr(self, "deaths"):   self.deaths.start()
            if hasattr(self, "unions"): self.unions.start() 
            if hasattr(self, "emotions"): self.emotions.start()

            self._sim_running = True
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")

            # El contador de UI lo basamos en el periodo del motor de cumpleaños
            self._countdown = getattr(self.birthday, "segundos_por_tick", 10)

            # Loops de UI
            self._tick_timer_loop()

            self._toast("▶ Simulación iniciada")
        except Exception as e:
            messagebox.showerror("Simulación", f"No se pudo iniciar la simulación:\n{e}")


    def _stop_sim(self):
        if not getattr(self, "_sim_running", False):
            return
        try:
            # Detén en orden (no es crítico, pero ayuda)
            if hasattr(self, "deaths"):   self.deaths.stop()
            if hasattr(self, "birthday"): self.birthday.stop()
            if hasattr(self, "births"): self.births.stop()
            if hasattr(self, "unions"): self.unions.stop()
            if hasattr(self, "emotions"): self.emotions.stop()
        except Exception:
            pass

        self._sim_running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self._toast("⏸ Simulación detenida")


    def _on_sim_change(self):
        self.after(0, self._redraw)

    def _on_sim_event(self, tipo, payload):
        """Llamado desde hilos de los motores → brincar a hilo UI."""
        self.after(0, self._handle_event, tipo, payload)

    def _tick_timer_loop(self):
        if not self._sim_running:
            self._update_timer_ui()
            return
        self._countdown -= 1
        if self._countdown <= 0:
            self._countdown = self.birthday.segundos_por_tick
        self._update_timer_ui()
        self.after(1000, self._tick_timer_loop)

    def _update_timer_ui(self):
        try:
            anio = self.birthday.anio_sim
        except Exception:
            anio = None
        anio_txt = str(anio) if anio else "—"
        c = max(0, int(self._countdown)) if hasattr(self, "_countdown") else "—"
        self.lbl_timer.config(text=f"Año sim: {anio_txt}  | Próximo tick: {c}s")

    def _handle_event(self, tipo, payload):
        # --- TOASTS
        ced = payload.get("cedula")
        p = self.personas.get(ced, {})
        nombre = p.get("nombre", ced or "¿?")

        if tipo == "fallece":
            nom = payload.get("nombre") or nombre
            edad = payload.get("edad")
            fecha = payload.get("fecha")
            extra = f" a los {edad}" if isinstance(edad, int) else ""
            fecha_txt = f" ({fecha})" if fecha else ""
            self._toast(f"💀 Falleció {nom}{extra}{fecha_txt}")

        elif tipo == "viudez":
            nom = payload.get("nombre") or nombre
            self._toast(f"🖤 {nom} ha quedado viudo/a")

        elif tipo == "union":
            self._toast(f"❤️ {payload.get('detalle','Se unieron')}")

        elif tipo in ("hijo", "nace"):
            if tipo == "nace":
                self._toast(f"🍼 Nacimiento: {payload.get('nombre_bebe','Bebé')}")
            else:
                self._toast(f"🍼 {payload.get('detalle','Nace un bebé')}")

        elif tipo == "tutoria":
            self._toast(f"🟢 {payload.get('detalle','Tutoría asignada')}")

        elif tipo == "separacion":
            self._toast(f"💔 {payload.get('detalle','Separación')}")

        elif tipo == "salud_baja":
            nivel = payload.get("nivel","")
            val = payload.get("valor","")
            self._toast(f"😟 Salud emocional {nivel} ({val})")

        elif tipo == "cumpleaños":
            # si quieres silenciar cumples, comenta este bloque:
            if getattr(self, "var_show_cumples", None) and self.var_show_cumples.get():
                self._toast(f"🎂 {nombre} {payload.get('detalle','cumple años')}")

        # --- PANEL DE EVENTOS (si está abierto) ---
        if getattr(self, "_event_panel", None) and self._event_panel.winfo_exists():
            try:
                anio = getattr(self.birthday, "anio_sim", None) or getattr(self.deaths, "anio_sim", None) or 0
                self._event_panel.log_event(anio, tipo, payload, self.personas)
            except Exception:
                pass

    def _toast(self, text, duration_ms: int = 3500):
        top = tk.Toplevel(self)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        try:
            top.attributes("-alpha", 0.94)
        except Exception:
            pass

        frm = tk.Frame(top, bg="#222", bd=0, highlightthickness=0)
        frm.pack(fill="both", expand=True)
        lbl = tk.Label(frm, text=text, bg="#222", fg="#fff", padx=14, pady=10, font=("Segoe UI", 10, "bold"), justify="left")
        lbl.pack()

        self.update_idletasks()
        sw = self.winfo_width()
        sh = self.winfo_height()
        rx = self.winfo_rootx()
        ry = self.winfo_rooty()
        w = 360
        h = 60
        x = rx + sw - w - 20
        y = ry + sh - h - 20
        top.geometry(f"{w}x{h}+{x}+{y}")

        top.after(duration_ms, top.destroy)

