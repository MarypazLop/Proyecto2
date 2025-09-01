import tkinter as tk
from tkinter import messagebox, ttk
from tkcalendar import DateEntry
import os
import random
from PIL import Image, ImageTk

# Archivos de datos
FAMILIAS_FILE = "familias.txt"
PERSONAS_FILE = "personas.txt"

# Provincias, géneros y estados civiles
PROVINCIAS = ["San José", "Alajuela", "Cartago", "Heredia", "Guanacaste", "Puntarenas", "Limón"]
GENEROS = ["Masculino", "Femenino", "Otro"]
ESTADOS_CIVILES = ["Soltero/a", "Casado/a", "Unión libre", "Divorciado/a", "Viudo/a"]
TIPOS_FILIACION = ["None","Biológico/a", "Adoptivo/a"]

class RegistroApp(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Sistema Árbol Genealógico - Registro")
        self.geometry("650x720")
        self.resizable(False, False)
        self.configure(bg="#f5f5dc")

        # Centrar ventana
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (650 // 2)
        y = (self.winfo_screenheight() // 2) - (720 // 2)
        self.geometry(f"+{x}+{y}")

        # Avatares
        self.avatar_dir = "Assets/personas"
        if not os.path.isdir(self.avatar_dir):
            os.makedirs(self.avatar_dir, exist_ok=True)
        self.avatars = [f for f in os.listdir(self.avatar_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        self.avatar_var = tk.StringVar(value=self.avatars[0] if self.avatars else "")

        # Estilo combobox
        style = ttk.Style(self)
        style.configure("Clean.TCombobox",
                        fieldbackground="#fff8dc",
                        background="#fff8dc",
                        borderwidth=0)

        # Frames
        self._crear_frames()
        self._crear_campos()
        self._crear_botones()
        self._actualizar_familias_combo()
        self._actualizar_padres_madres()

        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _crear_frames(self):
        self.frame_familia = tk.LabelFrame(self, text="Gestión de Familias", padx=10, pady=10, bg="#fff8dc", bd=2)
        self.frame_familia.pack(fill="x", padx=20, pady=10)

        self.frame_persona = tk.LabelFrame(self, text="Gestión de Integrantes", padx=10, pady=10, bg="#fff8dc", bd=2)
        self.frame_persona.pack(fill="x", padx=20, pady=10)

        # Asegurar dos columnas con igual peso visual
        for c in range(4):
            self.frame_persona.grid_columnconfigure(c, weight=1)

    def _crear_campos(self):
        pady = 8
        # ----- FAMILIA -----
        tk.Label(self.frame_familia, text="ID Familia:", bg="#fff8dc").grid(row=0, column=0, sticky="w", pady=pady)
        self.entry_id_familia = tk.Entry(self.frame_familia, state="readonly", bd=1, bg="#ffffff")
        self.entry_id_familia.grid(row=0, column=1, sticky="we")

        tk.Button(self.frame_familia, text="Generar ID", command=self.generar_id_familia)\
            .grid(row=0, column=2, padx=5, pady=pady)
        tk.Label(self.frame_familia, text="Nombre Familia:", bg="#fff8dc").grid(row=1, column=0, sticky="w", pady=pady)
        self.entry_nombre_familia = tk.Entry(self.frame_familia, bd=1, bg="#ffffff")
        self.entry_nombre_familia.grid(row=1, column=1, sticky="we", pady=pady)

        # ----- PERSONA (columna izquierda: 0-1) -----
        tk.Label(self.frame_persona, text="Cédula:", bg="#fff8dc")\
            .grid(row=0, column=0, sticky="e", pady=pady, padx=(0, 5))
        self.entry_cedula = tk.Entry(self.frame_persona, bd=1, bg="#ffffff")
        self.entry_cedula.grid(row=0, column=1, pady=pady, sticky="we")

        tk.Label(self.frame_persona, text="Nombre:", bg="#fff8dc")\
            .grid(row=1, column=0, sticky="e", pady=pady, padx=(0, 5))
        self.entry_nombre = tk.Entry(self.frame_persona, bd=1, bg="#ffffff")
        self.entry_nombre.grid(row=1, column=1, pady=pady, sticky="we")

        tk.Label(self.frame_persona, text="Fecha Nacimiento:", bg="#fff8dc")\
            .grid(row=2, column=0, sticky="e", pady=pady, padx=(0, 5))
        self.entry_nacimiento = DateEntry(self.frame_persona, date_pattern="yyyy-mm-dd", bd=1)
        self.entry_nacimiento.grid(row=2, column=1, pady=pady, sticky="we")

        tk.Label(self.frame_persona, text="Género:", bg="#fff8dc")\
            .grid(row=3, column=0, sticky="e", pady=pady, padx=(0, 5))
        self.genero_var = tk.StringVar(value=GENEROS[0])
        self.menu_genero = ttk.Combobox(self.frame_persona, textvariable=self.genero_var, values=GENEROS,
                                        state="readonly", style="Clean.TCombobox")
        self.menu_genero.grid(row=3, column=1, pady=pady, sticky="we")

        # Fallecido
        tk.Label(self.frame_persona, text="¿Falleció?", bg="#fff8dc")\
            .grid(row=4, column=0, sticky="e", pady=pady, padx=(0, 5))
        self.fallecido_var = tk.StringVar(value="No")
        self.combo_fallecido = ttk.Combobox(
            self.frame_persona,
            textvariable=self.fallecido_var,
            values=["Sí", "No"],
            state="readonly",
            style="Clean.TCombobox"
        )
        self.combo_fallecido.grid(row=4, column=1, pady=pady, sticky="we")

        # Fecha Fallecimiento
        tk.Label(self.frame_persona, text="Fecha de fallecimiento:", bg="#fff8dc")\
            .grid(row=5, column=0, sticky="e", pady=pady, padx=(10, 5))
        self.fecha_fallecimiento = DateEntry(self.frame_persona, state="disabled", date_pattern="yyyy-mm-dd")
        self.fecha_fallecimiento.grid(row=5, column=1, pady=pady, sticky="we")
        self.combo_fallecido.bind("<<ComboboxSelected>>", self._toggle_fecha_fallecimiento)

        # ----- PERSONA (columna derecha: 2-3) -----
        tk.Label(self.frame_persona, text="Provincia:", bg="#fff8dc")\
            .grid(row=0, column=2, sticky="e", pady=pady, padx=(10, 5))
        self.provincia_var = tk.StringVar(value=PROVINCIAS[0])
        self.menu_provincia = ttk.Combobox(self.frame_persona, textvariable=self.provincia_var, values=PROVINCIAS,
                                        state="readonly", style="Clean.TCombobox")
        self.menu_provincia.grid(row=0, column=3, pady=pady, sticky="we")

        tk.Label(self.frame_persona, text="Estado Civil:", bg="#fff8dc")\
            .grid(row=1, column=2, sticky="e", pady=pady, padx=(10, 5))
        self.estado_var = tk.StringVar(value="Soltero/a")
        self.menu_estado = ttk.Combobox(self.frame_persona, textvariable=self.estado_var,
                                        values=ESTADOS_CIVILES, state="readonly", style="Clean.TCombobox")
        self.menu_estado.grid(row=1, column=3, pady=pady, sticky="we")
        self.menu_estado.bind("<<ComboboxSelected>>", self._toggle_pareja)

        tk.Label(self.frame_persona, text="Pareja:", bg="#fff8dc")\
            .grid(row=2, column=2, sticky="e", pady=pady, padx=(10, 5))
        self.pareja_var = tk.StringVar()
        self.combo_pareja = ttk.Combobox(self.frame_persona, textvariable=self.pareja_var,
                                        state="disabled", style="Clean.TCombobox")
        self.combo_pareja.grid(row=2, column=3, pady=pady, sticky="we")

        tk.Label(self.frame_persona, text="Asignar a Familia:", bg="#fff8dc")\
            .grid(row=3, column=2, sticky="e", pady=pady, padx=(10, 5))
        self.familia_var = tk.StringVar()
        self.combo_familia = ttk.Combobox(self.frame_persona, textvariable=self.familia_var,
                                        state="readonly", style="Clean.TCombobox")
        self.combo_familia.grid(row=3, column=3, pady=pady, sticky="we")

        tk.Label(self.frame_persona, text="Padre:", bg="#fff8dc")\
            .grid(row=4, column=2, sticky="e", pady=pady, padx=(10, 5))
        self.padre_var = tk.StringVar()
        self.combo_padre = ttk.Combobox(self.frame_persona, textvariable=self.padre_var,
                                        state="readonly", style="Clean.TCombobox")
        self.combo_padre.grid(row=4, column=3, pady=pady, sticky="we")

        tk.Label(self.frame_persona, text="Madre:", bg="#fff8dc")\
            .grid(row=5, column=2, sticky="e", pady=pady, padx=(10, 5))
        self.madre_var = tk.StringVar()
        self.combo_madre = ttk.Combobox(self.frame_persona, textvariable=self.madre_var,
                                        state="readonly", style="Clean.TCombobox")
        self.combo_madre.grid(row=5, column=3, pady=pady, sticky="we")

        # ---- ÚNICO selector: Tipo de filiación (aplica a ambos) ----
        tk.Label(self.frame_persona, text="Tipo de filiación (padres):", bg="#fff8dc")\
            .grid(row=6, column=2, sticky="e", pady=pady, padx=(10, 5))
        self.filiacion_var = tk.StringVar(value="Biológico/a")
        self.combo_filiacion = ttk.Combobox(
            self.frame_persona, textvariable=self.filiacion_var,
            values=TIPOS_FILIACION, state="readonly", style="Clean.TCombobox"
        )
        self.combo_filiacion.grid(row=6, column=3, pady=pady, sticky="we")

        # Avatar (derecha, debajo)
        tk.Label(self.frame_persona, text="Avatar:", bg="#fff8dc")\
            .grid(row=7, column=2, sticky="e", pady=pady, padx=(10, 5))
        self.avatar_menu = ttk.Combobox(self.frame_persona, textvariable=self.avatar_var, values=self.avatars,
                                        state="readonly", style="Clean.TCombobox")
        self.avatar_menu.grid(row=7, column=3, pady=pady, sticky="we")

        self.avatar_preview = tk.Label(self.frame_persona, bg="#fff8dc")
        self.avatar_preview.grid(row=8, column=3, pady=(0, 5), sticky="e")

        self.avatar_var.trace_add("write", self._actualizar_preview)
        self._actualizar_preview()

    def _crear_botones(self):
        tk.Button(self.frame_familia, text="Registrar Familia", command=self.guardar_familia)\
            .grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(self.frame_persona, text="Registrar Persona", command=self.guardar_persona)\
            .grid(row=20, column=0, columnspan=2, pady=10, sticky="w")

    # ---------- Funciones ----------
    def generar_id_familia(self):
        nuevo_id = str(random.randint(1000, 9999))
        self.entry_id_familia.config(state="normal")
        self.entry_id_familia.delete(0, tk.END)
        self.entry_id_familia.insert(0, nuevo_id)
        self.entry_id_familia.config(state="readonly")

    def guardar_familia(self):
        fid = self.entry_id_familia.get().strip()
        nombre = self.entry_nombre_familia.get().strip()
        if not fid or not nombre:
            messagebox.showerror("Error", "Debe completar todos los campos de la familia.")
            return
        with open(FAMILIAS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{fid};{nombre}\n")
        messagebox.showinfo("Éxito", f"Familia '{nombre}' registrada.")
        self.entry_id_familia.config(state="normal")
        self.entry_id_familia.delete(0, tk.END)
        self.entry_id_familia.config(state="readonly")
        self.entry_nombre_familia.delete(0, tk.END)
        self._actualizar_familias_combo()

    # ========= UTILIDADES NUEVAS PARA PERSONAS =========
    def _leer_personas(self):
        filas = []
        if os.path.exists(PERSONAS_FILE):
            with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln:
                        filas.append(ln.split(";"))
        return filas

    def _guardar_personas(self, filas):
        with open(PERSONAS_FILE, "w", encoding="utf-8") as f:
            for campos in filas:
                f.write(";".join(campos) + "\n")

    def _buscar_idx_por_cedula(self, filas, ced):
        # orden: 0:familia 1:cedula 2:nombre 3:nac 4:fallec 5:genero 6:prov 7:estado 8:avatar 9:padre 10:madre 11:pareja 12:filiacion
        for i, campos in enumerate(filas):
            if len(campos) > 1 and campos[1] == ced:
                return i
        return -1

    def _cedula_de_combo(self, s):
        # valores tipo "123456 - Nombre Apellido" -> devuelve "123456"
        if not s:
            return ""
        return s.split(" - ", 1)[0].strip()

    def _fid_de_combo_familia(self, s):
        # valores tipo "1001 - Pérez" -> devuelve "1001"
        if not s:
            return ""
        return s.split(" - ", 1)[0].strip()

    # ========= GUARDAR PERSONA (con validaciones y sincronización) =========
    def guardar_persona(self):
        cedula = self.entry_cedula.get().strip()
        nombre = self.entry_nombre.get().strip()
        nacimiento_date = self.entry_nacimiento.get_date()  # DateEntry te da date
        nacimiento = nacimiento_date.strftime("%Y-%m-%d")
        fallecimiento = self.fecha_fallecimiento.get_date().strftime("%Y-%m-%d") if self.fallecido_var.get() == "Sí" else ""
        genero = self.genero_var.get()
        provincia = self.provincia_var.get()
        familia = self.familia_var.get()
        avatar = self.avatar_var.get()
        estado = self.estado_var.get()
        padre = self.padre_var.get() if self.padre_var.get() != "None" else ""
        madre = self.madre_var.get() if self.madre_var.get() != "None" else ""
        pareja = self.pareja_var.get() if self.pareja_var.get() else ""
        filiacion = "" if self.filiacion_var.get() == "None" else self.filiacion_var.get()

        # (Aquí puedes mantener tus validaciones de coherencia estado/padres/pareja, etc.)

        filas = self._leer_personas()
        idx = self._buscar_idx_por_cedula(filas, cedula)

        nueva = (idx == -1)
        prev_falle = "" if nueva else (filas[idx][4] if len(filas[idx]) > 4 else "")

        campos = [
            self._fid_de_combo_familia(familia),  # 0
            cedula,                                # 1
            nombre,                                # 2
            nacimiento,                            # 3
            fallecimiento,                         # 4
            genero,                                # 5
            provincia,                             # 6
            estado,                                # 7
            avatar,                                # 8
            self._cedula_de_combo(padre),          # 9
            self._cedula_de_combo(madre),          # 10
            self._cedula_de_combo(pareja),         # 11
            filiacion                               # 12
        ]

        if nueva:
            filas.append(campos)
        else:
            filas[idx] = campos

        # Guardar a disco
        self._guardar_personas(filas)

        # === Historial ===
        # NACIMIENTO solo al crear por primera vez
        if nueva:
            try:
                from history import rec_nacimiento
                rec_nacimiento(
                    cedula,
                    f"Nació en {provincia}",
                    fecha=nacimiento_date  # fecha real de nacimiento
                )
            except Exception as e:
                print("Historial (nacimiento) no registrado:", e)

        # FALLECIMIENTO:
        # - Si es nuevo y ya viene con fallecimiento -> registrar.
        # - Si es edición y antes estaba vacío y ahora trae fecha -> registrar.
        try:
            if fallecimiento:
                from datetime import datetime
                falle_date = datetime.strptime(fallecimiento, "%Y-%m-%d").date()
                # calcular edad al fallecer (opcional, bonito para historial)
                edad = falle_date.year - nacimiento_date.year - (
                    (falle_date.month, falle_date.day) < (nacimiento_date.month, nacimiento_date.day)
                )

                should_record_death = nueva or (not prev_falle)
                if should_record_death:
                    from history import rec_fallecimiento
                    rec_fallecimiento(cedula, f"Falleció ({edad} años)", fecha=falle_date)
        except Exception as e:
            print("Historial (fallecimiento) no registrado:", e)

        messagebox.showinfo("Éxito", f"Persona '{nombre}' registrada con estado civil '{estado}'.")
        self._limpiar_formulario()
        self._actualizar_padres_madres()

    def _actualizar_padres_madres(self):
        personas = []
        if os.path.exists(PERSONAS_FILE):
            with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    datos = line.split(";")
                    # Solo necesitamos cédula y nombre
                    if len(datos) >= 3:
                        cedula, nombre = datos[1], datos[2]
                        personas.append(f"{cedula} - {nombre}")
        self.combo_padre["values"] = ["None"] + personas
        self.combo_madre["values"] = ["None"] + personas
        self.combo_pareja["values"] = personas
        self.padre_var.set("None")
        self.madre_var.set("None")
        self.pareja_var.set("")

    def _limpiar_formulario(self):
        self.entry_cedula.delete(0, tk.END)
        self.entry_nombre.delete(0, tk.END)
        self.entry_nacimiento.set_date("2000-01-01")
        self.fallecido_var.set("No")
        self._toggle_fecha_fallecimiento()
        self.genero_var.set(GENEROS[0])
        self.provincia_var.set(PROVINCIAS[0])
        self.estado_var.set("Soltero/a")
        self.familia_var.set("")
        if self.avatars:
            self.avatar_var.set(self.avatars[0])
        else:
            self.avatar_var.set("")
        self.padre_var.set("None")
        self.madre_var.set("None")
        self.pareja_var.set("")
        self.filiacion_var.set("None")
        self._actualizar_preview()

    def _toggle_fecha_fallecimiento(self, event=None):
        if self.fallecido_var.get() == "Sí":
            self.fecha_fallecimiento.config(state="normal")
        else:
            self.fecha_fallecimiento.config(state="disabled")

    def _toggle_pareja(self, event=None):
        estado = self.estado_var.get()
        if estado in ["Casado/a", "Unión libre"]:  # quitamos "Viudo/a" para coherencia
            self.combo_pareja.config(state="readonly")
            personas = []
            if os.path.exists(PERSONAS_FILE):
                with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        datos = line.split(";")
                        if len(datos) >= 3:
                            cedula, nombre = datos[1], datos[2]
                            personas.append(f"{cedula} - {nombre}")
            self.combo_pareja["values"] = personas
            if personas:
                self.pareja_var.set(personas[0])
        else:
            self.combo_pareja.set("")
            self.combo_pareja.config(state="disabled")

    def _actualizar_familias_combo(self):
        familias = []
        if os.path.exists(FAMILIAS_FILE):
            with open(FAMILIAS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    partes = line.split(";")
                    if len(partes) >= 2:
                        fid, nombre = partes[0], partes[1]
                        familias.append(f"{fid} - {nombre}")
        self.combo_familia["values"] = familias
        if familias:
            self.familia_var.set(familias[0])

    def _actualizar_preview(self, *args):
        """Muestra preview del avatar si existe."""
        if not self.avatar_var.get():
            self.avatar_preview.config(image="", text="(Sin avatar)")
            return
        avatar_file = os.path.join(self.avatar_dir, self.avatar_var.get())
        if os.path.exists(avatar_file):
            try:
                img = Image.open(avatar_file).resize((80, 80))
                self.avatar_img = ImageTk.PhotoImage(img)
                self.avatar_preview.config(image=self.avatar_img, text="")
            except Exception as e:
                self.avatar_preview.config(image="", text=f"Error avatar:\n{e}")
        else:
            self.avatar_preview.config(image="", text="(Archivo no encontrado)")

