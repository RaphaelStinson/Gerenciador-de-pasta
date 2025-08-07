import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import shutil
import time
import threading
import json
import pystray
from PIL import Image, ImageDraw
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Importações específicas para Windows
import sys
if sys.platform == 'win32':
    import win32com.client
    import pythoncom

# Mapa de extensões padrão, usado apenas na primeira execução
DEFAULT_EXTENSION_MAP = {
    '.jpg': 'Imagens', '.jpeg': 'Imagens', '.png': 'Imagens', '.gif': 'Imagens',
    '.bmp': 'Imagens', '.svg': 'Imagens', '.webp': 'Imagens', '.tiff': 'Imagens',
    '.pdf': 'Documentos', '.docx': 'Documentos', '.doc': 'Documentos',
    '.txt': 'Documentos', '.pptx': 'Apresentações', '.xlsx': 'Planilhas',
    '.csv': 'Planilhas', '.odt': 'Documentos',
    '.mp4': 'Vídeos', '.mov': 'Vídeos', '.avi': 'Vídeos', '.mkv': 'Vídeos',
    '.mp3': 'Áudios', '.wav': 'Áudios', '.flac': 'Áudios', '.aac': 'Áudios',
    '.zip': 'Compactados', '.rar': 'Compactados', '.7z': 'Compactados', '.gz': 'Compactados',
    '.exe': 'Executáveis', '.msi': 'Instaladores',
    '.py': 'Scripts Python', '.js': 'Scripts JavaScript', '.html': 'Web', '.css': 'Web'
}

CONFIG_FILE = "config.json"

class FileOrganizerHandler(FileSystemEventHandler):
    """Manipula os eventos do sistema de arquivos."""
    def __init__(self, watch_directory, app_instance):
        self.watch_directory = watch_directory
        self.app = app_instance

    def on_created(self, event):
        if not event.is_directory:
            time.sleep(1)
            self.process(event.src_path)

    def process(self, file_path):
        """Processa e move um único arquivo."""
        try:
            if not os.path.exists(file_path): return
            filename = os.path.basename(file_path)
            if filename.startswith('.') or filename.startswith('~'): return

            _, file_extension = os.path.splitext(filename)
            file_extension = file_extension.lower()

            if file_extension:
                dest_folder_name = self.app.extension_map.get(file_extension, f"Arquivos {file_extension.replace('.', '').upper()}")
                dest_folder_path = os.path.join(self.watch_directory, dest_folder_name)

                if not os.path.exists(dest_folder_path):
                    os.makedirs(dest_folder_path)
                    self.app.log_message(f"Pasta '{dest_folder_name}' criada em '{os.path.basename(self.watch_directory)}'.")

                shutil.move(file_path, os.path.join(dest_folder_path, filename))
                self.app.log_message(f"'{filename}' movido para '{dest_folder_name}'.")
        except Exception as e:
            self.app.log_message(f"Erro ao processar '{os.path.basename(file_path)}': {e}")

class App(ctk.CTk):
    def __init__(self, start_minimized=False):
        super().__init__()

        self.title("Organizador de Arquivos Automático")
        self.geometry("800x700")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # Lista de pastas
        self.grid_rowconfigure(4, weight=1) # Log

        # --- Variáveis de Estado ---
        self.target_directories = []
        self.extension_map = {}
        self.observers = []
        self.monitoring_thread = None
        self.is_monitoring = False
        self.autostart_var = tk.BooleanVar()
        self.startup_var = tk.BooleanVar() # Nova variável para iniciar com Windows
        self.tray_icon = None
        self.extensions_window = None

        self.create_widgets()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # Se o app for iniciado com o argumento para minimizar, esconde a janela após um breve momento.
        if start_minimized:
            self.after(100, self.hide_window)

    def create_widgets(self):
        # --- Frame de Controles Superior ---
        top_controls_frame = ctk.CTkFrame(self)
        top_controls_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="ew")
        top_controls_frame.grid_columnconfigure((0, 1), weight=1)

        self.add_folder_button = ctk.CTkButton(top_controls_frame, text="Adicionar Pasta", command=self.add_folder)
        self.add_folder_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        self.manage_extensions_button = ctk.CTkButton(top_controls_frame, text="Gerenciar Extensões", command=self.open_extensions_window)
        self.manage_extensions_button.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # --- Frame com a Lista de Pastas ---
        self.folder_list_frame = ctk.CTkScrollableFrame(self, label_text="Pastas Monitoradas")
        self.folder_list_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="nsew")
        self.folder_list_frame.grid_columnconfigure(0, weight=1)

        # --- Frame de Controles (Iniciar/Parar) ---
        bottom_controls_frame = ctk.CTkFrame(self)
        bottom_controls_frame.grid(row=3, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        bottom_controls_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_button = ctk.CTkButton(bottom_controls_frame, text="Iniciar Monitoramento", command=self.start_monitoring, state="disabled")
        self.start_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.stop_button = ctk.CTkButton(bottom_controls_frame, text="Parar Monitoramento", command=self.stop_monitoring, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        self.autostart_checkbox = ctk.CTkCheckBox(bottom_controls_frame, text="Iniciar monitoramento ao abrir", variable=self.autostart_var, command=self.save_config)
        self.autostart_checkbox.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        
        self.startup_checkbox = ctk.CTkCheckBox(bottom_controls_frame, text="Iniciar com o Windows", variable=self.startup_var, command=self.toggle_startup)
        self.startup_checkbox.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        if sys.platform != 'win32':
            self.startup_checkbox.configure(state="disabled", text="Iniciar com o Windows (Apenas no Windows)")

        # --- Caixa de Log ---
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.log_textbox.grid(row=4, column=0, columnspan=2, padx=20, pady=(10, 20), sticky="nsew")

    # --- Lógica de Configuração e Inicialização com Windows ---
    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.target_directories = config.get("folders", [])
                    self.autostart_var.set(config.get("autostart", False))
                    self.extension_map = config.get("extensions", DEFAULT_EXTENSION_MAP.copy())
                self.log_message("Configurações carregadas.")
            else:
                self.extension_map = DEFAULT_EXTENSION_MAP.copy()
                self.log_message("Nenhum arquivo de configuração encontrado. Usando padrões.")

            if sys.platform == 'win32':
                self.startup_var.set(self.check_if_startup_shortcut_exists())

            self.update_folder_list_ui()
            self.update_button_states()
            
            if self.autostart_var.get() and self.target_directories:
                self.start_monitoring()
        except Exception as e:
            self.log_message(f"Erro ao carregar config: {e}")
            self.extension_map = DEFAULT_EXTENSION_MAP.copy()

    def save_config(self):
        config = {"folders": self.target_directories, "autostart": self.autostart_var.get(), "extensions": self.extension_map}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        self.log_message("Configurações salvas.")

    def get_startup_folder_path(self):
        return os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')

    def get_shortcut_path(self):
        return os.path.join(self.get_startup_folder_path(), "OrganizadorDeArquivos.lnk")

    def check_if_startup_shortcut_exists(self):
        return os.path.exists(self.get_shortcut_path())

    def toggle_startup(self):
        if sys.platform != 'win32':
            self.log_message("Funcionalidade 'Iniciar com o Windows' está disponível apenas no Windows.")
            return

        shortcut_path = self.get_shortcut_path()
        # Quando compilado, sys.executable é o caminho para o .exe
        executable_path = sys.executable

        try:
            if self.startup_var.get():
                self.log_message("Adicionando à inicialização do Windows...")
                pythoncom.CoInitialize()
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.TargetPath = executable_path
                # Adiciona o argumento para iniciar minimizado
                shortcut.Arguments = "--start-minimized"
                shortcut.WorkingDirectory = os.path.dirname(executable_path)
                shortcut.IconLocation = executable_path
                shortcut.save()
                pythoncom.CoUninitialize()
                self.log_message("Programa configurado para iniciar com o Windows (minimizando na bandeja).")
            else:
                if os.path.exists(shortcut_path):
                    self.log_message("Removendo da inicialização do Windows...")
                    os.remove(shortcut_path)
                    self.log_message("Programa removido da inicialização do Windows.")
        except Exception as e:
            self.log_message(f"Erro ao configurar inicialização: {e}")
            messagebox.showerror("Erro", f"Ocorreu um erro ao configurar a inicialização com o Windows.\n\n{e}\n\nTente executar o programa como administrador.")
            self.startup_var.set(not self.startup_var.get())

    # --- Lógica da Janela de Extensões ---
    def open_extensions_window(self):
        if self.extensions_window is not None and self.extensions_window.winfo_exists():
            self.extensions_window.focus()
            return
        self.extensions_window = ctk.CTkToplevel(self)
        self.extensions_window.title("Gerenciar Extensões")
        self.extensions_window.geometry("600x500")
        self.extensions_window.transient(self)
        add_frame = ctk.CTkFrame(self.extensions_window)
        add_frame.pack(padx=10, pady=10, fill="x")
        ext_entry = ctk.CTkEntry(add_frame, placeholder_text=".ext (ex: .zip)")
        ext_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        folder_entry = ctk.CTkEntry(add_frame, placeholder_text="Nome da Pasta (ex: Compactados)")
        folder_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        add_button = ctk.CTkButton(add_frame, text="Adicionar", width=80, command=lambda: self.add_new_mapping(ext_entry.get(), folder_entry.get(), ext_entry, folder_entry))
        add_button.pack(side="left", padx=5, pady=5)
        list_frame = ctk.CTkScrollableFrame(self.extensions_window, label_text="Regras Atuais")
        list_frame.pack(padx=10, pady=10, expand=True, fill="both")
        self.populate_extensions_list(list_frame)

    def populate_extensions_list(self, list_frame):
        for widget in list_frame.winfo_children(): widget.destroy()
        sorted_extensions = sorted(self.extension_map.items())
        for i, (ext, folder) in enumerate(sorted_extensions):
            item_frame = ctk.CTkFrame(list_frame)
            item_frame.pack(fill="x", padx=5, pady=2)
            item_frame.grid_columnconfigure(0, weight=1)
            label = ctk.CTkLabel(item_frame, text=f"{ext:<15} -> {folder}", font=ctk.CTkFont(family="monospace"))
            label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
            remove_button = ctk.CTkButton(item_frame, text="Remover", width=80, fg_color="red", hover_color="darkred", command=lambda e=ext: self.remove_mapping(e, list_frame))
            remove_button.grid(row=0, column=1, padx=10, pady=5, sticky="e")

    def add_new_mapping(self, ext, folder, ext_entry, folder_entry):
        if not ext or not folder:
            messagebox.showwarning("Aviso", "Ambos os campos devem ser preenchidos.", parent=self.extensions_window)
            return
        if not ext.startswith('.'): ext = '.' + ext
        ext = ext.lower()
        self.extension_map[ext] = folder
        self.save_config()
        self.populate_extensions_list(self.extensions_window.winfo_children()[1])
        ext_entry.delete(0, "end")
        folder_entry.delete(0, "end")

    def remove_mapping(self, ext, list_frame):
        if ext in self.extension_map:
            del self.extension_map[ext]
            self.save_config()
            self.populate_extensions_list(list_frame)

    # --- Lógica Principal da Aplicação ---
    def add_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected and folder_selected not in self.target_directories:
            self.target_directories.append(folder_selected)
            self.update_folder_list_ui()
            self.update_button_states()
            self.save_config()

    def remove_folder(self, folder_to_remove):
        self.target_directories.remove(folder_to_remove)
        self.update_folder_list_ui()
        self.update_button_states()
        self.save_config()

    def update_folder_list_ui(self):
        for widget in self.folder_list_frame.winfo_children(): widget.destroy()
        for i, folder in enumerate(self.target_directories):
            item_frame = ctk.CTkFrame(self.folder_list_frame)
            item_frame.pack(fill="x", padx=5, pady=2)
            item_frame.grid_columnconfigure(0, weight=1)
            label = ctk.CTkLabel(item_frame, text=folder, wraplength=550)
            label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
            remove_button = ctk.CTkButton(item_frame, text="Remover", width=80, command=lambda f=folder: self.remove_folder(f))
            remove_button.grid(row=0, column=1, padx=10, pady=5, sticky="e")

    def start_monitoring(self):
        if not self.target_directories:
            messagebox.showwarning("Aviso", "Adicione pelo menos uma pasta para monitorar.")
            return
        if self.is_monitoring: return
        self.is_monitoring = True
        self.update_button_states()
        def monitor_task():
            self.observers = []
            for directory in self.target_directories:
                self.organize_existing_files(directory)
                event_handler = FileOrganizerHandler(directory, self)
                observer = Observer()
                observer.schedule(event_handler, directory, recursive=False)
                observer.start()
                self.observers.append(observer)
            self.log_message("Monitoramento em tempo real iniciado.")
            while self.is_monitoring: time.sleep(1)
            for observer in self.observers:
                observer.stop()
                observer.join()
            self.log_message("Monitoramento parado.")
        self.monitoring_thread = threading.Thread(target=monitor_task, daemon=True)
        self.monitoring_thread.start()

    def stop_monitoring(self):
        if self.is_monitoring:
            self.is_monitoring = False
            self.update_button_states()

    def organize_existing_files(self, directory):
        self.log_message(f"Organizando arquivos existentes em: {directory}")
        handler = FileOrganizerHandler(directory, self)
        try:
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path): handler.process(file_path)
            self.log_message(f"Organização inicial de '{os.path.basename(directory)}' concluída.")
        except Exception as e:
            self.log_message(f"Erro na organização inicial: {e}")

    def update_button_states(self):
        has_folders = bool(self.target_directories)
        if self.is_monitoring:
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.add_folder_button.configure(state="disabled")
            self.manage_extensions_button.configure(state="disabled")
            self.autostart_checkbox.configure(state="disabled")
            if sys.platform == 'win32': self.startup_checkbox.configure(state="disabled")
            for item_frame in self.folder_list_frame.winfo_children():
                item_frame.winfo_children()[1].configure(state="disabled")
        else:
            self.start_button.configure(state="normal" if has_folders else "disabled")
            self.stop_button.configure(state="disabled")
            self.add_folder_button.configure(state="normal")
            self.manage_extensions_button.configure(state="normal")
            self.autostart_checkbox.configure(state="normal")
            if sys.platform == 'win32': self.startup_checkbox.configure(state="normal")
            for item_frame in self.folder_list_frame.winfo_children():
                item_frame.winfo_children()[1].configure(state="normal")

    def log_message(self, message):
        def _update_log():
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", f"{message}\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
        self.after(0, _update_log)

    # --- Lógica da Bandeja do Sistema ---
    def create_tray_image(self):
        width, height, color1, color2 = 64, 64, (20, 20, 120), (100, 180, 255)
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle((width // 4, height // 4, width * 3 // 4, height * 3 // 4), fill=color2)
        return image

    def setup_tray_icon(self):
        icon_image = self.create_tray_image()
        menu = pystray.Menu(pystray.MenuItem('Mostrar', self.show_window, default=True), pystray.MenuItem('Sair', self.quit_app))
        self.tray_icon = pystray.Icon("organizador", icon_image, "Organizador de Arquivos", menu)
        self.tray_icon.run()

    def hide_window(self):
        self.withdraw()
        threading.Thread(target=self.setup_tray_icon, daemon=True).start()

    def show_window(self):
        if self.tray_icon: self.tray_icon.stop()
        self.deiconify()

    def quit_app(self):
        if self.extensions_window: self.extensions_window.destroy()
        self.save_config()
        if self.tray_icon: self.tray_icon.stop()
        if self.is_monitoring:
            self.stop_monitoring()
            if self.monitoring_thread: self.monitoring_thread.join(timeout=2)
        self.destroy()

if __name__ == "__main__":
    # Verifica se o argumento --start-minimized foi passado
    start_minimized_arg = '--start-minimized' in sys.argv

    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = App(start_minimized=start_minimized_arg)
    app.mainloop()