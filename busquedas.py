# -*- coding: utf-8 -*-
"""
Ventana de Consultas (QueriesApp)
- Carga familias y personas desde TXT
- Usa kinship.Kinship para resolver parentescos
- Consultas por Persona A (padres, hijos, etc.)
- Relación A ↔ B
- Consultas globales (b, c, d)
- NUEVAS: Antepasados maternos de X; Descendientes vivos de X
- NUEVO (punto 3): Historial de eventos por persona (sidecar historial.txt)
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
from kinship import Kinship

# Reutilizamos rutas como en tree.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAMILIAS_FILE = os.path.join(BASE_DIR, "familias.txt")
PERSONAS_FILE = os.path.join(BASE_DIR, "personas.txt")

# ------------------ Utilidades ------------------

def _id_from_combo(text: str) -> str:
    if not text:
        return ""
    return text.split(" - ")[0].strip()

def _load_familias():
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

def _load_personas():
    p = {}
    if os.path.exists(PERSONAS_FILE):
        with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = line.split(";")
                # 0:fam 1:cedula 2:nombre 3:nac 4:falle 5:genero 6:provincia
                # 7:estado 8:avatar 9:padre 10:madre 11:pareja 12:filiacion
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
                    "filiacion": d[12].strip(),
                    # Campo opcional para familias extra (si lo usas en tree.py)
                    "familias_extra": []
                }
    return p

def _person_label(ced: str, personas: dict) -> str:
    if not ced:
        return ""
    p = personas.get(ced, {})
    return f"{ced} - {p.get('nombre', ced)}"

def _parse_date_relaxed(s: str):
    """Acepta 'YYYY-MM-DD', 'YYYY/MM/DD', 'DD/MM/YYYY' o 'YYYY'. Devuelve date o None."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def _strip_accents_lower(s: str) -> str:
    table = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")
    return (s or "").translate(table).lower().strip()

def _is_alive(p: dict) -> bool:
    return not (p.get("falle") or "").strip()

# ------------------ Ventana ------------------

class QueriesApp(tk.Toplevel):
    """
    Ventana de consultas de parentesco:
    - Persona A: consultas de 1 entrada (padres, hijos, etc.)
    - Persona B: etiqueta de relación A ↔ B
    - Filtro por familia para listas más cortas
    - Consultas globales (b, c, d) que no dependen de A/B
    - NUEVO: Antepasados maternos de X; Descendientes vivos de X
    - NUEVO: Historial de A
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Family Tree - Queries")
        self.geometry("980x640")
        self.minsize(880, 560)
        self.configure(bg="#f5f5dc")

        # Data
        self.familias = _load_familias()
        self.personas = _load_personas()
        self.kin = Kinship(self.personas)

        # --- UI layout ---
        container = tk.Frame(self, bg="#f5f5dc")
        container.pack(fill="both", expand=True, padx=12, pady=10)

        # Fila superior: selects
        top = tk.Frame(container, bg="#f5f5dc")
        top.pack(fill="x", pady=(0, 10))

        tk.Label(top, text="Familia:", bg="#f5f5dc").grid(row=0, column=0, sticky="w")
        self.sel_familia = tk.StringVar()
        fam_values = [f"{fid} - {name}" for fid, name in self.familias]
        self.cmb_familia = ttk.Combobox(top, textvariable=self.sel_familia, values=fam_values, state="readonly", width=40)
        self.cmb_familia.grid(row=0, column=1, padx=6, sticky="w")
        self.cmb_familia.bind("<<ComboboxSelected>>", self._refill_people)

        tk.Label(top, text="Persona A:", bg="#f5f5dc").grid(row=0, column=2, padx=(16, 0), sticky="e")
        self.sel_a = tk.StringVar()
        self.cmb_a = ttk.Combobox(top, textvariable=self.sel_a, state="readonly", width=44)
        self.cmb_a.grid(row=0, column=3, padx=6, sticky="w")

        tk.Label(top, text="Persona B:", bg="#f5f5dc").grid(row=0, column=4, padx=(16, 0), sticky="e")
        self.sel_b = tk.StringVar()
        self.cmb_b = ttk.Combobox(top, textvariable=self.sel_b, state="readonly", width=44)
        self.cmb_b.grid(row=0, column=5, padx=6, sticky="w")

        # Botonera (consultas de una persona)
        cmds = tk.LabelFrame(container, text="Consultas (Persona A)", bg="#fff8dc")
        cmds.pack(fill="x", pady=(0, 10))

        btns = [
            ("Padres", self.q_parents),
            ("Hijos", self.q_children),
            ("Cónyuge", self.q_spouse),
            ("Hermanos (completos)", self.q_full_sibs),
            ("Medios hermanos", self.q_half_sibs),
            ("Abuelos", self.q_grandparents),
            ("Nietos", self.q_grandchildren),
            ("Tíos/Tías", self.q_uncles_aunts),
            ("Primos", self.q_cousins),
            ("Sobrinos", self.q_nieces_nephews),
            # --- NUEVOS ---
            ("Antepasados maternos", self.q_maternal_ancestors),
            ("Descendientes vivos", self.q_living_descendants),
            ("Historial de A", self.q_history_for_a),  # <<--- NUEVO (punto 3)
        ]
        for i, (txt, fn) in enumerate(btns):
            tk.Button(cmds, text=txt, command=fn, width=22).grid(row=i//3, column=i%3, padx=6, pady=6, sticky="w")

        # Segunda fila: relación A ↔ B
        relation = tk.LabelFrame(container, text="Relación entre A y B", bg="#fff8dc")
        relation.pack(fill="x", pady=(0, 10))
        tk.Button(relation, text="Etiquetar relación A ↔ B", command=self.q_relation, width=25).grid(row=0, column=0, padx=6, pady=6, sticky="w")

        # Consultas globales (b, c, d)
        global_box = tk.LabelFrame(container, text="Consultas globales", bg="#fff8dc")
        global_box.pack(fill="x", pady=(0, 10))

        tk.Button(global_box, text="(b) Nacidos últimos 10 años", command=self.q_births_last_10y, width=28)\
            .grid(row=0, column=0, padx=6, pady=6, sticky="w")

        tk.Button(global_box, text="(c) Parejas actuales con ≥2 hijos", command=self.q_couples_two_plus_children, width=32)\
            .grid(row=0, column=1, padx=6, pady=6, sticky="w")

        tk.Button(global_box, text="(d) Fallecidos antes de 50 años", command=self.q_died_before_50, width=30)\
            .grid(row=0, column=2, padx=6, pady=6, sticky="w")

        # Resultados
        results = tk.LabelFrame(container, text="Resultados", bg="#fff8dc")
        results.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(results, bg="#fffaf0")
        self.listbox.pack(fill="both", expand=True, padx=8, pady=8)

        # Cargar combos
        if self.familias:
            self.sel_familia.set(fam_values[0])
        self._refill_people()

    # ---------------- helpers ----------------
    def _people_for_family(self, fam_id: str):
        ceds = [
            ced for ced, p in self.personas.items()
            if p.get("familia", "") == fam_id or fam_id in (p.get("familias_extra") or [])
        ]
        ceds = sorted(set(ceds), key=lambda c: self.personas[c]["nombre"].lower())
        return [_person_label(c, self.personas) for c in ceds]

    def _refill_people(self, *_):
        fam_id = _id_from_combo(self.sel_familia.get())
        values = self._people_for_family(fam_id) if fam_id else [
            _person_label(c, self.personas) for c in sorted(self.personas.keys())
        ]
        self.cmb_a["values"] = values
        self.cmb_b["values"] = values
        if values:
            self.sel_a.set(values[0])
            if len(values) > 1:
                self.sel_b.set(values[1])

    def _get_ced_a(self):
        return _id_from_combo(self.sel_a.get())

    def _get_ced_b(self):
        return _id_from_combo(self.sel_b.get())

    def _fill(self, rows):
        self.listbox.delete(0, tk.END)
        if not rows:
            self.listbox.insert(tk.END, "— Sin resultados —")
            return
        for r in rows:
            self.listbox.insert(tk.END, r)

    # ---------------- consultas (A) ----------------
    def q_parents(self):
        a = self._get_ced_a()
        fa, ma = self.kin.get_parents(a)
        out = []
        if fa: out.append("Padre:  " + _person_label(fa, self.personas))
        if ma: out.append("Madre:  " + _person_label(ma, self.personas))
        self._fill(out)

    def q_children(self):
        a = self._get_ced_a()
        rows = [_person_label(c, self.personas) for c in sorted(self.kin.get_children(a))]
        self._fill(rows)

    def q_spouse(self):
        a = self._get_ced_a()
        b = self.kin.get_spouse(a)
        self._fill([_person_label(b, self.personas)] if b else [])

    def q_full_sibs(self):
        a = self._get_ced_a()
        rows = [_person_label(c, self.personas) for c in sorted(self.kin.full_siblings(a))]
        self._fill(rows)

    def q_half_sibs(self):
        a = self._get_ced_a()
        rows = [_person_label(c, self.personas) for c in sorted(self.kin.half_siblings(a))]
        self._fill(rows)

    def q_grandparents(self):
        a = self._get_ced_a()
        rows = [_person_label(c, self.personas) for c in sorted(self.kin.grandparents(a))]
        self._fill(rows)

    def q_grandchildren(self):
        a = self._get_ced_a()
        rows = [_person_label(c, self.personas) for c in sorted(self.kin.grandchildren(a))]
        self._fill(rows)

    def q_uncles_aunts(self):
        a = self._get_ced_a()
        rows = [_person_label(c, self.personas) for c in sorted(self.kin.uncles_aunts(a, include_inlaws=True))]
        self._fill(rows)

    def q_cousins(self):
        a = self._get_ced_a()
        rows = [_person_label(c, self.personas) for c in sorted(self.kin.cousins(a))]
        self._fill(rows)

    def q_nieces_nephews(self):
        a = self._get_ced_a()
        rows = [_person_label(c, self.personas) for c in sorted(self.kin.nieces_nephews(a))]
        self._fill(rows)

    # ---------- NUEVO: Antepasados maternos ----------
    def _maternal_ancestors_chain(self, ced: str):
        """
        Retorna lista de cédulas siguiendo solo la línea materna:
        madre -> abuela materna -> bisabuela materna -> ...
        """
        chain = []
        seen = set()
        current = ced
        while True:
            p = self.personas.get(current)
            if not p:
                break
            mom = (p.get("madre") or "").strip()
            # por si viene en formato "123 - Nombre"
            mom = mom.split(" - ")[0].strip() if mom else ""
            if not mom or mom in seen:
                break
            seen.add(mom)
            chain.append(mom)
            current = mom
        return chain

    def q_maternal_ancestors(self):
        a = self._get_ced_a()
        ceds = self._maternal_ancestors_chain(a)
        rows = [_person_label(c, self.personas) for c in ceds]
        self._fill(rows)

    # ---------- NUEVO: Descendientes vivos ----------
    def _all_descendants(self, root_ced: str):
        """
        Retorna conjunto de todas las cédulas descendientes de root_ced:
        hijos, nietos, bisnietos, ...
        """
        out = set()
        queue = [root_ced]
        while queue:
            cur = queue.pop(0)
            for child in sorted(self.kin.get_children(cur)):
                if child not in out:
                    out.add(child)
                    queue.append(child)
        out.discard(root_ced)
        return out

    def q_living_descendants(self):
        a = self._get_ced_a()
        desc = self._all_descendants(a)
        vivos = [c for c in desc if _is_alive(self.personas.get(c, {}))]
        rows = [_person_label(c, self.personas) for c in sorted(vivos)]
        self._fill(rows)

    # ---------- NUEVO (punto 3): Historial de A ----------
    def _format_event_row(self, e):
        try:
            f = e["fecha"].strftime("%Y-%m-%d")
        except Exception:
            f = str(e.get("fecha", ""))
        return f"{f}  |  {e.get('tipo','').upper()}  |  {e.get('detalle','').strip()}"

    def q_history_for_a(self):
        a = self._get_ced_a()
        if not a:
            self._fill(["Seleccione Persona A"])
            return
        # Import local para no romper si history.py no está
        try:
            from history import get_history
            evts = get_history(a)
        except Exception:
            evts = []
        if not evts:
            self._fill([_person_label(a, self.personas), "—", "— Sin eventos registrados —"])
            return
        rows = [_person_label(a, self.personas), "—"]
        rows.extend(self._format_event_row(e) for e in evts)
        self._fill(rows)

    # ---------- Relación A ↔ B (robusta) ----------
    def q_relation(self):
        a = self._get_ced_a()
        b = self._get_ced_b()
        if not a or not b:
            self._fill(["Seleccione Persona A y Persona B."])
            return
        try:
            # Si tu clase Kinship tiene un etiquetador especializado:
            rel = self.kin.label_relationship(a, b)  # puede no existir en tu versión
        except Exception:
            # Fallback simple con relaciones básicas
            if b in self.kin.get_children(a):
                rel = "Progenitor ↔ Hijo/a"
            elif a in self.kin.get_children(b):
                rel = "Hijo/a ↔ Progenitor"
            elif self.kin.get_spouse(a) == b:
                rel = "Pareja"
            else:
                # hermanos completos o medios
                if b in self.kin.full_siblings(a):
                    rel = "Hermanos (completos)"
                elif b in self.kin.half_siblings(a):
                    rel = "Medios hermanos"
                else:
                    rel = "Sin relación directa conocida"
        self._fill([f"{_person_label(a, self.personas)} ↔ {_person_label(b, self.personas)}: {rel}"])

    # ---------------- Consultas globales (b, c, d) ----------------
    def q_births_last_10y(self):
        """
        (b) ¿Cuántas personas nacieron en los últimos 10 años?
        Lista nombres y total.
        """
        today = date.today()
        cutoff = date(today.year - 10, today.month, today.day)
        rows = []
        count = 0
        for ced, p in self.personas.items():
            nac = _parse_date_relaxed(p.get("nac", ""))
            if nac and nac >= cutoff:
                rows.append(_person_label(ced, self.personas))
                count += 1
        rows.append(f"— Total: {count}")
        self._fill(rows)

        # (Opcional) podrías filtrar por familia seleccionada:
        # fam_id = _id_from_combo(self.sel_familia.get())
        # ... y aplicar solo a personas de esa familia

    def q_couples_two_plus_children(self):
        """
        (c) ¿Cuáles parejas actuales tienen 2 o más hijos en común?
        Busca estado conyugal activo y cuenta hijos donde ambos figuran como padre/madre.
        """
        # Índice rápido: (padre, madre) -> set(hijos)
        common_children = {}
        for ced, p in self.personas.items():
            padre = (p.get("padre") or "").split(" - ")[0].strip()
            madre = (p.get("madre") or "").split(" - ")[0].strip()
            if padre or madre:
                key = (padre or "-", madre or "-")
                common_children.setdefault(key, set()).add(ced)

        rows = []
        seen_pairs = set()
        for ced, p in self.personas.items():
            # pareja actual (casado/a o unión libre)
            if p.get("estado") not in ("Casado/a", "Unión libre"):
                continue
            a = ced
            b = (p.get("pareja") or "").split(" - ")[0].strip()
            if not b or b not in self.personas:
                continue
            # pareja sin duplicar
            pair = tuple(sorted([a, b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            # Hijos en común (considerando ambos roles)
            kids = set()
            # Buscar en índice donde (padre, madre) coincida en cualquier orden
            for (fa, ma), hijos in common_children.items():
                sfa = fa if fa != "-" else ""
                sma = ma if ma != "-" else ""
                if {sfa, sma} == {a, b}:
                    kids |= hijos
            if len(kids) >= 2:
                rows.append(f"{_person_label(a, self.personas)} ❤ {_person_label(b, self.personas)}  → hijos en común: {len(kids)}")

        if not rows:
            rows = ["— Sin parejas con ≥ 2 hijos en común —"]
        self._fill(rows)

    def q_died_before_50(self):
        """
        (d) ¿Cuántas personas fallecieron antes de cumplir 50 años?
        Muestra lista y total.
        """
        rows = []
        count = 0
        for ced, p in self.personas.items():
            nac = _parse_date_relaxed(p.get("nac", ""))
            falle = _parse_date_relaxed(p.get("falle", ""))
            if nac and falle:
                age = falle.year - nac.year - ((falle.month, falle.day) < (nac.month, nac.day))
                if age < 50:
                    rows.append(_person_label(ced, self.personas) + f"  († {age} años)")
                    count += 1
        rows.append(f"— Total: {count}")
        self._fill(rows)
