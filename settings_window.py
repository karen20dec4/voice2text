import customtkinter as ctk
from tkinter import messagebox
from config import save_config
from audio_recorder import AudioRecorder
from hotkey import parse_hotkey

def open_on_any_click(combo):
    """A read-only CTkComboBox opens only from its arrow; let its text area open the list too."""
    entry = combo._entry
    entry.configure(cursor="hand2")
    entry.bind("<Button-1>", lambda event: combo._clicked(event) or "break")
    entry.bind("<Enter>", combo._on_enter, add="+")
    entry.bind("<Leave>", combo._on_leave, add="+")
    return combo


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_config, on_save_callback=None):
        super().__init__(parent)
        self.config = current_config
        self.on_save_callback = on_save_callback

        self.title("Setări Voice2Text")
        height = min(620, self.winfo_screenheight() - 100)
        self.geometry(f"450x{height}")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 450) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        pad_x = 24
        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True)

        title_label = ctk.CTkLabel(
            content,
            text="⚙️ Configurare Dictare Vocală",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(20, 15))

        # Model Whisper
        lbl_model = ctk.CTkLabel(content, text="Model Whisper (Calitate vs Viteză):", anchor="w")
        lbl_model.pack(fill="x", padx=pad_x, pady=(5, 2))

        self.models_map = {
            "small (Recomandat - Precizie mare)": "small",
            "base (Rapid - PC-uri mai vechi)": "base",
            "medium (Acuratețe maximă - Recomandat cu GPU)": "medium",
            "tiny (Ultra-rapid)": "tiny"
        }
        model_display = [k for k, v in self.models_map.items() if v == self.config.get("model_size", "small")]
        cur_model_str = model_display[0] if model_display else list(self.models_map.keys())[0]

        self.cb_model = open_on_any_click(ctk.CTkComboBox(content, values=list(self.models_map.keys()), width=400, state="readonly"))
        self.cb_model.set(cur_model_str)
        self.cb_model.pack(fill="x", padx=pad_x, pady=(0, 10))

        # Procesare
        lbl_device = ctk.CTkLabel(content, text="Procesare:", anchor="w")
        lbl_device.pack(fill="x", padx=pad_x, pady=(5, 2))

        self.compute_map = {
            "GPU (placă video, CPU dacă nu merge)": "gpu",
            "CPU": "cpu"
        }
        compute_display = [k for k, v in self.compute_map.items() if v == self.config.get("compute_device", "gpu")]
        cur_compute_str = compute_display[0] if compute_display else list(self.compute_map.keys())[0]

        self.cb_compute = open_on_any_click(ctk.CTkComboBox(content, values=list(self.compute_map.keys()), width=400, state="readonly"))
        self.cb_compute.set(cur_compute_str)
        self.cb_compute.pack(fill="x", padx=pad_x, pady=(0, 10))

        # Limba
        lbl_lang = ctk.CTkLabel(content, text="Limba de dictare:", anchor="w")
        lbl_lang.pack(fill="x", padx=pad_x, pady=(5, 2))

        self.lang_map = {
            "Română (ro)": "ro",
            "Engleză (en)": "en",
            "Detectare automată (auto)": "auto"
        }
        lang_display = [k for k, v in self.lang_map.items() if v == self.config.get("language", "ro")]
        cur_lang_str = lang_display[0] if lang_display else "Română (ro)"

        self.cb_lang = open_on_any_click(ctk.CTkComboBox(content, values=list(self.lang_map.keys()), width=400, state="readonly"))
        self.cb_lang.set(cur_lang_str)
        self.cb_lang.pack(fill="x", padx=pad_x, pady=(0, 10))

        # Microfon
        lbl_mic = ctk.CTkLabel(content, text="Microfon de intrare:", anchor="w")
        lbl_mic.pack(fill="x", padx=pad_x, pady=(5, 2))

        devices = AudioRecorder.get_input_devices()
        self.dev_map = {"[Implicit din Windows]": None}
        for idx, name in devices:
            self.dev_map[name] = idx

        cur_dev_idx = self.config.get("device_index")
        cur_dev_str = "[Implicit din Windows]"
        if cur_dev_idx is not None:
            for name, idx in self.dev_map.items():
                if idx == cur_dev_idx:
                    cur_dev_str = name
                    break

        self.cb_mic = open_on_any_click(ctk.CTkComboBox(content, values=list(self.dev_map.keys()), width=400, state="readonly"))
        self.cb_mic.set(cur_dev_str)
        self.cb_mic.pack(fill="x", padx=pad_x, pady=(0, 10))

        # Shortcut tastatură
        lbl_hotkey = ctk.CTkLabel(content, text="Shortcut Tastatură (ex: f9, ctrl+alt+space, alt+d):", anchor="w")
        lbl_hotkey.pack(fill="x", padx=pad_x, pady=(5, 2))

        self.entry_hotkey = ctk.CTkEntry(content, width=400)
        self.entry_hotkey.insert(0, self.config.get("hotkey", "f9"))
        self.entry_hotkey.pack(fill="x", padx=pad_x, pady=(0, 15))

        # Checkboxes
        self.var_floating = ctk.BooleanVar(value=self.config.get("floating_visible", True))
        self.chk_floating = ctk.CTkCheckBox(content, text="Afișează butonul plutitor pe ecran", variable=self.var_floating)
        self.chk_floating.pack(anchor="w", padx=pad_x, pady=(0, 8))

        self.var_space = ctk.BooleanVar(value=self.config.get("add_trailing_space", True))
        self.chk_space = ctk.CTkCheckBox(content, text="Adaugă un spațiu la finalul textului dictat", variable=self.var_space)
        self.chk_space.pack(anchor="w", padx=pad_x, pady=(0, 8))

        self.var_enter = ctk.BooleanVar(value=self.config.get("auto_enter", False))
        self.chk_enter = ctk.CTkCheckBox(content, text="Apasă automat tasta Enter după tastare", variable=self.var_enter)
        self.chk_enter.pack(anchor="w", padx=pad_x, pady=(0, 8))

        self.var_strip = ctk.BooleanVar(value=self.config.get("strip_diacritics", False))
        self.chk_strip = ctk.CTkCheckBox(
            content, text="Scrie fără diacritice (ă→a, ș→s), pentru servere fără UTF-8",
            variable=self.var_strip)
        self.chk_strip.pack(anchor="w", padx=pad_x, pady=(0, 20))

        # Action buttons
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(fill="x", padx=pad_x, pady=(5, 15))

        btn_save = ctk.CTkButton(
            btn_frame,
            text="💾 Salvează și Aplică",
            fg_color="#1f6feb",
            hover_color="#1158c7",
            command=self._save
        )
        btn_save.pack(side="left", expand=True, fill="x", padx=(0, 5))

        btn_cancel = ctk.CTkButton(
            btn_frame,
            text="Anulează",
            fg_color="#30363d",
            hover_color="#444c56",
            command=self.destroy
        )
        btn_cancel.pack(side="right", expand=True, fill="x", padx=(5, 0))

    def _save(self):
        new_model = self.models_map.get(self.cb_model.get(), "small")
        new_compute = self.compute_map.get(self.cb_compute.get(), "gpu")
        new_lang = self.lang_map.get(self.cb_lang.get(), "ro")
        new_mic = self.dev_map.get(self.cb_mic.get(), None)
        new_hotkey = self.entry_hotkey.get().strip().lower() or "f9"
        new_floating = self.var_floating.get()
        new_space = self.var_space.get()
        new_enter = self.var_enter.get()
        new_strip = self.var_strip.get()

        new_config = self.config.copy()
        new_config.update(model_size=new_model, compute_device=new_compute, language=new_lang, device_index=new_mic,
                          hotkey=new_hotkey, floating_visible=new_floating,
                          add_trailing_space=new_space, auto_enter=new_enter,
                          strip_diacritics=new_strip)
        try:
            parse_hotkey(new_hotkey)
            if self.on_save_callback:
                self.on_save_callback(new_config)
            else:
                save_config(new_config)
        except Exception as error:
            messagebox.showerror("Setările nu au fost aplicate", str(error), parent=self)
            return
        self.destroy()
