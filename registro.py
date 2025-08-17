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
ESTADOS_CIVILES = ["Soltero/a", "Casado/a", "Divorciado/a", "Viudo/a"]

# ------------------ CLASE DEL REGISTRO ------------------
class RegistroApp(tk.Toplevel):
    def __init__(self, parent):

        super().__init__(parent)
        self.title("Sistema Árbol Genealógico - Registro")
        self.geometry("650x650")
        self.resizable(False, False)
        self.configure(bg="#f5f5dc")  # Color de fondo

        # Centrar ventana
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (650 // 2)
        y = (self.winfo_screenheight() // 2) - (650 // 2)
        self.geometry(f"+{x}+{y}")

        self.avatar_dir = "Assets/personas"
        self.avatars = [f for f in os.listdir(self.avatar_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        self.avatar_var = tk.StringVar(value=self.avatars[0] if self.avatars else "")

        # ---------- ESTILO LIMPIO PARA COMBOBOX ----------
        style = ttk.Style(self)
        style.configure("Clean.TCombobox",
                        fieldbackground="#fff8dc",  # mismo color que fondo
                        background="#fff8dc",
                        borderwidth=0)
        # -------------------------------------------------

        self._crear_frames()
        self._crear_campos()
        self._crear_botones()
        self._actualizar_familias_combo()

        # Evita que se pase atrás del menú
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _crear_frames(self):
        self.frame_familia = tk.LabelFrame(self, text="Gestión de Familias", padx=10, pady=10, bg="#fff8dc", bd=2)
        self.frame_familia.pack(fill="x", padx=20, pady=10)

        self.frame_persona = tk.LabelFrame(self, text="Gestión de Integrantes", padx=10, pady=10, bg="#fff8dc", bd=2)
        self.frame_persona.pack(fill="x", padx=20, pady=10)

    # -------- CREAR CAMPOS --------
    def _crear_campos(self):
        pady = 8  # Espaciado vertical entre campos

        style = ttk.Style()
        style.configure("Clean.TCombobox",
                        fieldbackground="#ffffff",
                        background="#ffffff",
                        borderwidth=1)

        # ------------------ Familias ------------------
        tk.Label(self.frame_familia, text="ID Familia:", bg="#fff8dc", fg="#000000").grid(row=0, column=0, sticky="w", pady=pady)
        self.entry_id_familia = tk.Entry(self.frame_familia, state="readonly", bd=1, bg="#ffffff")
        self.entry_id_familia.grid(row=0, column=1)
        self.btn_generar_id = tk.Button(self.frame_familia, text="Generar ID", command=self.generar_id_familia)
        self.btn_generar_id.grid(row=0, column=2, padx=5, pady=pady)

        tk.Label(self.frame_familia, text="Nombre Familia:", bg="#fff8dc", fg="#000000").grid(row=1, column=0, sticky="w", pady=pady)
        self.entry_nombre_familia = tk.Entry(self.frame_familia, bd=1, bg="#ffffff")
        self.entry_nombre_familia.grid(row=1, column=1, pady=pady)

        # ------------------ Personas ------------------
        tk.Label(self.frame_persona, text="Cédula:", bg="#fff8dc", fg="#000000").grid(row=0, column=0, sticky="w", pady=pady)
        self.entry_cedula = tk.Entry(self.frame_persona, bd=1, bg="#ffffff")
        self.entry_cedula.grid(row=0, column=1, pady=pady)

        tk.Label(self.frame_persona, text="Nombre:", bg="#fff8dc", fg="#000000").grid(row=1, column=0, sticky="w", pady=pady)
        self.entry_nombre = tk.Entry(self.frame_persona, bd=1, bg="#ffffff")
        self.entry_nombre.grid(row=1, column=1, pady=pady)

        tk.Label(self.frame_persona, text="Fecha Nacimiento:", bg="#fff8dc", fg="#000000").grid(row=2, column=0, sticky="w", pady=pady)
        self.entry_nacimiento = DateEntry(self.frame_persona, date_pattern="yyyy-mm-dd", bd=1, bg="#ffffff")
        self.entry_nacimiento.grid(row=2, column=1, pady=pady)

        # Fallecimiento
        tk.Label(self.frame_persona, text="¿Fallecido?", bg="#fff8dc", fg="#000000").grid(row=3, column=0, sticky="w", pady=pady)
        self.fallecido_var = tk.StringVar(value="No")
        self.combo_fallecido = ttk.Combobox(self.frame_persona, textvariable=self.fallecido_var,
                                            values=["No","Sí"], state="readonly", style="Clean.TCombobox")
        self.combo_fallecido.grid(row=3, column=1, pady=pady)
        self.combo_fallecido.bind("<<ComboboxSelected>>", self._toggle_fecha_fallecimiento)
        self.label_fallecimiento = tk.Label(self.frame_persona, text="Fecha Fallecimiento:", bg="#fff8dc", fg="#000000")
        self.entry_fallecimiento = DateEntry(self.frame_persona, date_pattern="yyyy-mm-dd", bd=1, bg="#ffffff")

        # Género
        tk.Label(self.frame_persona, text="Género:", bg="#fff8dc", fg="#000000").grid(row=5, column=0, sticky="w", pady=pady)
        self.genero_var = tk.StringVar(value=GENEROS[0])
        self.menu_genero = ttk.Combobox(self.frame_persona, textvariable=self.genero_var, values=GENEROS,
                                        state="readonly", style="Clean.TCombobox")
        self.menu_genero.grid(row=5, column=1, pady=pady)

        # Provincia
        tk.Label(self.frame_persona, text="Provincia:", bg="#fff8dc", fg="#000000").grid(row=6, column=0, sticky="w", pady=pady)
        self.provincia_var = tk.StringVar(value=PROVINCIAS[0])
        self.menu_provincia = ttk.Combobox(self.frame_persona, textvariable=self.provincia_var, values=PROVINCIAS,
                                        state="readonly", style="Clean.TCombobox")
        self.menu_provincia.grid(row=6, column=1, pady=pady)

        # Estado civil
        tk.Label(self.frame_persona, text="Estado Civil:", bg="#fff8dc", fg="#000000").grid(row=7, column=0, sticky="w", pady=pady)
        self.estado_var = tk.StringVar(value=ESTADOS_CIVILES[0])
        self.menu_estado = ttk.Combobox(self.frame_persona, textvariable=self.estado_var, values=ESTADOS_CIVILES,
                                        state="readonly", style="Clean.TCombobox")
        self.menu_estado.grid(row=7, column=1, pady=pady)

        # Asignar a familia
        tk.Label(self.frame_persona, text="Asignar a Familia:", bg="#fff8dc", fg="#000000").grid(row=8, column=0, sticky="w", pady=pady)
        self.familia_var = tk.StringVar()
        self.combo_familia = ttk.Combobox(self.frame_persona, textvariable=self.familia_var, state="readonly", style="Clean.TCombobox")
        self.combo_familia.grid(row=8, column=1, pady=pady)

        # Avatar
        tk.Label(self.frame_persona, text="Avatar:", bg="#fff8dc", fg="#000000").grid(row=9, column=0, sticky="w", pady=pady)
        self.avatar_var = tk.StringVar()
        self.avatar_menu = ttk.Combobox(self.frame_persona, textvariable=self.avatar_var, values=self.avatars,
                                        state="readonly", style="Clean.TCombobox")
        self.avatar_menu.grid(row=9, column=1, pady=pady)
        self.avatar_preview = tk.Label(self.frame_persona, bg="#fff8dc")
        self.avatar_preview.grid(row=9, column=2, padx=10)
        self.avatar_var.trace_add("write", self._actualizar_preview)
        self._actualizar_preview()


    # -------- CREAR BOTONES --------
    def _crear_botones(self):
        self.btn_guardar_familia = tk.Button(self.frame_familia, text="Registrar Familia", command=self.guardar_familia)
        self.btn_guardar_familia.grid(row=2, column=0, columnspan=2, pady=10)

        self.btn_guardar_persona = tk.Button(self.frame_persona, text="Registrar Persona", command=self.guardar_persona)
        self.btn_guardar_persona.grid(row=10, column=0, columnspan=2, pady=10)

    # -------- FUNCIONES --------
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

    def guardar_persona(self):
        cedula = self.entry_cedula.get().strip()
        nombre = self.entry_nombre.get().strip()
        nacimiento = self.entry_nacimiento.get_date().strftime("%Y-%m-%d")
        fallecimiento = self.entry_fallecimiento.get_date().strftime("%Y-%m-%d") if self.fallecido_var.get()=="Sí" else ""
        genero = self.genero_var.get()
        provincia = self.provincia_var.get()
        estado = self.estado_var.get()
        familia = self.familia_var.get()
        avatar = self.avatar_var.get()

        if not cedula or not nombre or not nacimiento or not genero or not provincia or not estado or not familia or not avatar:
            messagebox.showerror("Error", "Debe completar todos los campos obligatorios.")
            return

        with open(PERSONAS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{familia};{cedula};{nombre};{nacimiento};{fallecimiento};{genero};{provincia};{estado};{avatar}\n")
        messagebox.showinfo("Éxito", f"Persona '{nombre}' registrada en familia {familia}.")
        self._limpiar_formulario()

    def _limpiar_formulario(self):
        self.entry_cedula.delete(0, tk.END)
        self.entry_nombre.delete(0, tk.END)
        self.entry_nacimiento.set_date("")
        self.fallecido_var.set("No")
        self._toggle_fecha_fallecimiento()
        self.genero_var.set(GENEROS[0])
        self.provincia_var.set(PROVINCIAS[0])
        self.estado_var.set(ESTADOS_CIVILES[0])
        self.familia_var.set("")
        self.avatar_var.set(self.avatars[0] if self.avatars else "")
        self._actualizar_preview()

    def _toggle_fecha_fallecimiento(self, event=None):
        if self.fallecido_var.get() == "Sí":
            self.label_fallecimiento.grid(row=4, column=0, sticky="w", pady=5)
            self.entry_fallecimiento.grid(row=4, column=1, pady=5)
        else:
            self.label_fallecimiento.grid_remove()
            self.entry_fallecimiento.grid_remove()

    def _actualizar_familias_combo(self):
        familias = []
        if os.path.exists(FAMILIAS_FILE):
            with open(FAMILIAS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    fid, nombre = line.strip().split(";")
                    familias.append(f"{fid} - {nombre}")
        self.combo_familia["values"] = familias
        if familias:
            self.familia_var.set(familias[0])

    def _actualizar_preview(self, *args):
        if not self.avatar_var.get(): return
        avatar_file = os.path.join(self.avatar_dir, self.avatar_var.get())
        if os.path.exists(avatar_file):
            img = Image.open(avatar_file).resize((50,50))
            self.avatar_img = ImageTk.PhotoImage(img)
            self.avatar_preview.config(image=self.avatar_img)
