# panel.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import csv

TIPO_COLORES = {
    "fallece":    ("#ffffff", "#e53935"),  # blanco sobre rojo
    "viudez":     ("#000000", "#ffd54f"),
    "nace":       ("#000000", "#a5d6a7"),
    "hijo":       ("#263238", "#c8e6c9"),
    "union":      ("#263238", "#ffccbc"),
    "separacion": ("#ffffff", "#8e24aa"),
    "tutoria":    ("#263238", "#fff59d"),
    "salud_baja": ("#263238", "#b3e5fc"),
    "cumpleaños": ("#0d47a1", "#e3f2fd"),
    "default":    ("#263238", "#eceff1"),
}

class EventPanel(tk.Toplevel):
    """
    Panel flotante para listar eventos de simulación agrupados por año.
    - Mostrar/ocultar cumpleaños (para evitar spam).
    - Auto scroll al final en cada inserción.
    - Exportar CSV.
    """

    def __init__(self, master, *, show_birthdays=False, auto_scroll=True):
        super().__init__(master)
        self.title("Panel de eventos")
        self.geometry("680x420")
        self.minsize(560, 360)
        self.configure(bg="#f7f3e9")
        self.attributes("-topmost", False)

        self.show_birthdays = tk.BooleanVar(value=bool(show_birthdays))
        self.auto_scroll = tk.BooleanVar(value=bool(auto_scroll))

        # Toolbar
        bar = tk.Frame(self, bg="#f7f3e9")
        bar.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Checkbutton(bar, text="Mostrar cumpleaños", variable=self.show_birthdays).pack(side="left", padx=(0,8))
        ttk.Checkbutton(bar, text="Auto-scroll", variable=self.auto_scroll).pack(side="left", padx=(0,8))

        ttk.Button(bar, text="Exportar CSV", command=self._export_csv).pack(side="left", padx=4)
        ttk.Button(bar, text="Limpiar", command=self._clear).pack(side="left", padx=4)
        ttk.Button(bar, text="Cerrar", command=self._close).pack(side="right", padx=4)

        # Treeview
        cols = ("Año", "Tipo", "Persona(s)", "Detalle")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for i, c in enumerate(cols):
            self.tree.heading(c, text=c)
            w = (70, 110, 210, 320)[i]
            self.tree.column(c, width=w, stretch=True)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=(8,0), pady=(0,8))
        vsb.pack(side="left", fill="y", padx=(0,8), pady=(0,8))

        # Estilos de filas por tipo
        style = ttk.Style(self)
        style.map("Treeview", background=[("selected", "#b3e5fc")])

        # Guardamos filas para exportar
        self._rows = []  # cada row: (anio, tipo, personas, detalle)

        # Cerrar limpio
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- API pública ----------
    def log_event(self, anio: int, tipo: str, payload: dict, personas: dict):
        """
        Inserta una fila representando 'tipo' con info derivada de 'payload' y 'personas'.
        anio: año de simulación en el momento del evento.
        """
        tipo = (tipo or "default").strip().lower()
        if tipo == "cumpleaños" and not self.show_birthdays.get():
            # Suprimimos cumpleaños si no quieren verlo
            return

        # Derivar persona(s) y detalle
        personas_txt, detalle = self._format_row(tipo, payload, personas)

        # Insertar
        values = (anio, tipo, personas_txt, detalle)
        self._rows.append(values)

        tag = tipo if tipo in TIPO_COLORES else "default"
        self._ensure_tag(tag)

        self.tree.insert("", "end", values=values, tags=(tag,))

        if self.auto_scroll.get():
            self.tree.see(self.tree.get_children()[-1])  # scroll al final

    # ---------- Aux ----------
    def _ensure_tag(self, tag):
        if getattr(self, f"_tag_{tag}", None):
            return
        fg, bg = TIPO_COLORES.get(tag, TIPO_COLORES["default"])
        try:
            self.tree.tag_configure(tag, foreground=fg, background=bg)
        except Exception:
            pass
        setattr(self, f"_tag_{tag}", True)

    def _pname(self, cid: str, personas: dict) -> str:
        if not cid: return ""
        p = personas.get(cid, {})
        n = p.get("nombre", "")
        return n or cid

    def _from_ced(self, payload, personas) -> str:
        cid = str(payload.get("cedula","") or "").strip()
        return self._pname(cid, personas)

    def _format_row(self, tipo: str, payload: dict, personas: dict):
        # Default
        personas_txt = self._from_ced(payload, personas)
        detalle = payload.get("detalle", "")

        if tipo == "fallece":
            nom = payload.get("nombre") or personas_txt
            edad = payload.get("edad")
            fecha = payload.get("fecha")
            extra = f" a los {edad}" if isinstance(edad, int) else ""
            fecha_txt = f" ({fecha})" if fecha else ""
            personas_txt = nom
            detalle = f"Fallece{extra}{fecha_txt}"

        elif tipo == "viudez":
            nom = payload.get("nombre") or personas_txt
            personas_txt = nom
            detalle = "Ha quedado viudo/a"

        elif tipo == "nace":
            bebe = payload.get("nombre_bebe") or personas_txt
            padre = payload.get("padre", "")
            madre = payload.get("madre", "")
            personas_txt = bebe
            detalle = f"Hijo/a de {madre} y {padre}"

        elif tipo == "hijo":
            nom = self._from_ced(payload, personas)
            personas_txt = nom
            # detalle ya viene

        elif tipo == "union":
            a_nom = payload.get("a_nombre", "")
            b_nom = payload.get("b_nombre", "")
            personas_txt = f"{a_nom} + {b_nom}".strip(" +")
            sc = payload.get("score")
            detalle = f"Se unieron (compat {sc:.0%})" if isinstance(sc, (int, float)) else "Se unieron"

        elif tipo == "separacion":
            # detalle esperado
            pass

        elif tipo == "tutoria":
            # detalle esperado con tutor
            pass

        elif tipo == "salud_baja":
            nivel = payload.get("nivel")
            val = payload.get("valor")
            personas_txt = self._from_ced(payload, personas)
            if nivel or val:
                detalle = f"Salud emocional {nivel} ({val})"

        elif tipo == "cumpleaños":
            nom = self._from_ced(payload, personas)
            edad = payload.get("edad")
            personas_txt = nom
            detalle = f"Cumple {edad}" if edad is not None else "Cumpleaños"

        return personas_txt, detalle

    def _export_csv(self):
        if not self._rows:
            messagebox.showinfo("Exportar CSV", "No hay eventos para exportar.")
            return
        path = filedialog.asksaveasfilename(
            title="Exportar eventos a CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Año", "Tipo", "Persona(s)", "Detalle"])
                w.writerows(self._rows)
            messagebox.showinfo("Exportar CSV", f"Eventos exportados a:\n{path}")
        except Exception as e:
            messagebox.showerror("Exportar CSV", f"No se pudo exportar:\n{e}")

    def _clear(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self._rows.clear()

    def _close(self):
        try:
            self.withdraw()
        except Exception:
            self.destroy()
