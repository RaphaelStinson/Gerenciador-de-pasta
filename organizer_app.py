import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import shutil
import time
import threading
import json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
# Novas importações para o ícone da bandeja do sistema
import pystray
from PIL import Image, ImageDraw

# Mapeamento de extensões para nomes de pastas mais amigáveis.
EXTENSION_MAP = {
    # Imagens
    '.jpg': 'Imagens', '.jpeg': 'Imagens', '.png': 'Imagens', '.gif': 'Imagens',
    '.bmp': 'Imagens', '.svg': 'Imagens', '.webp': 'Imagens', '.tiff': 'Imagens',
    # Documentos
    '.pdf': 'Documentos', '.docx': 'Documentos', '.doc': 'Documentos',
    '.txt': 'Documentos', '.pptx': 'Apresentações', '.xlsx': 'Planilhas',
    '.csv': 'Planilhas', '.odt': 'Documentos',
    # Vídeos
    '.mp4': 'Vídeos', '.mov': 'Vídeos', '.avi': 'Vídeos', '.mkv': 'Vídeos',
    # Áudio
    '.mp3': 'Áudios', '.wav': 'Áudios', '.flac': 'Áudios', '.aac': 'Áudios',
    # Arquivos Compactados
    '.zip': 'Compactados', '.rar': 'Compactados', '.7z': 'Compactados', '.gz': 'Compactados',
    # Executáveis e Instaladores
    '.exe': 'Executáveis', '.msi': 'Instaladores',
    # Código e Desenvolvimento
    '.py': 'Scripts Python', '.js': 'Scripts JavaScript', '.html': 'Web', '.css': 'Web'
}

CONFIG_FILE = "config.json"

class FileOrganizerHandler(FileSystemEventHandler):
    """Manipula os eventos do sistema de arquivos (criação de arquivos)."""
    def __init__(self, watch_directory, app_instance):
        self.watch_directory = watch_directory
        self.app = app_instance

    def on_created(self, event):
        if not event.is_directory:
            time.sleep(1) # Garante que o arquivo foi completamente escrito
            self.process(event.src_path)

    def process(self, file_path):
        """Processa e move um único arquivo para a pasta de destino apropriada."""
        try:
            if not os.path.exists(file_path):
                return
            filename = os.path.basename(file_path)
            if filename.startswith('.') or filename.startswith('~'):
                return

            _, file_extension = os.path.splitext(filename)
            file_extension = file_extension.lower()

            if file_extension:
                dest_folder_name = EXTENSION_MAP.get(file_extension, f"Arquivos {file_extension.replace('.', '').upper()}")
                dest_folder_path = os.path.join(self.watch_directory, dest_folder_name)

                if not os.path.exists(dest_folder_path):
                    os.makedirs(dest_folder_path)
                    self.app.log_message(f"Pasta '{dest_folder_name}' criada em '{os.path.basename(self.watch_directory)}'.")

                shutil.move(file_path, os.path.join(dest_folder_path, filename))
                self.app.log_message(f"'{filename}' movido para '{dest_folder_name}'.")
        except Exception as e:
            self.app.log_message(f"Erro ao processar '{os.path.basename(file_path)}': {e}")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Organizador de Arquivos Automático")
        self.geometry("800x600")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # --- Variáveis de Estado ---
        self.target_directories = []
        self.observers = []
        self.monitoring_thread = None
        self.is_monitoring = False
        self.autostart_var = tk.BooleanVar()
        self.tray_icon = None

        self.create_widgets()
        self.load_config()
        # Modificado para rodar em segundo plano ao fechar
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

    def create_widgets(self):
        # --- Frame de Controles Superior ---
        top_controls_frame = ctk.CTkFrame(self)
        top_controls_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        top_controls_frame.grid_columnconfigure(0, weight=1)

        self.add_folder_button = ctk.CTkButton(top_controls_frame, text="Adicionar Pasta para Monitorar", command=self.add_folder)
        self.add_folder_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        # --- Frame com a Lista de Pastas ---
        self.folder_list_frame = ctk.CTkScrollableFrame(self, label_text="Pastas Monitoradas")
        self.folder_list_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.folder_list_frame.grid_columnconfigure(0, weight=1)

        # --- Frame de Controles (Iniciar/Parar) ---
        bottom_controls_frame = ctk.CTkFrame(self)
        bottom_controls_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        bottom_controls_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_button = ctk.CTkButton(bottom_controls_frame, text="Iniciar Monitoramento", command=self.start_monitoring, state="disabled")
        self.start_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.stop_button = ctk.CTkButton(bottom_controls_frame, text="Parar Monitoramento", command=self.stop_monitoring, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        self.autostart_checkbox = ctk.CTkCheckBox(bottom_controls_frame, text="Iniciar monitoramento ao abrir", variable=self.autostart_var, command=self.save_config)
        self.autostart_checkbox.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        # --- Caixa de Log ---
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.log_textbox.grid(row=3, column=0, padx=20, pady=(10, 20), sticky="nsew")

    def create_tray_image(self):
        """Cria uma imagem simples para o ícone da bandeja."""
        width = 64
        height = 64
        color1 = (20, 20, 120)  # Azul escuro
        color2 = (100, 180, 255) # Azul claro
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle(
            (width // 4, height // 4, width * 3 // 4, height * 3 // 4),
            fill=color2)
        return image

    def setup_tray_icon(self):
        """Configura e inicia o ícone na bandeja do sistema."""
        icon_image = self.create_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem('Mostrar', self.show_window, default=True),
            pystray.MenuItem('Sair', self.quit_app)
        )
        self.tray_icon = pystray.Icon("organizador", icon_image, "Organizador de Arquivos", menu)
        self.tray_icon.run()

    def hide_window(self):
        """Esconde a janela principal e mostra o ícone na bandeja."""
        self.withdraw()
        # Inicia o ícone da bandeja em uma thread para não bloquear a GUI
        threading.Thread(target=self.setup_tray_icon, daemon=True).start()

    def show_window(self):
        """Para o ícone da bandeja e mostra a janela principal."""
        if self.tray_icon:
            self.tray_icon.stop()
        self.deiconify()

    def quit_app(self):
        """Fecha a aplicação completamente."""
        self.save_config()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.is_monitoring:
            self.stop_monitoring()
            if self.monitoring_thread:
                self.monitoring_thread.join(timeout=2)
        self.destroy()

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.target_directories = config.get("folders", [])
                    self.autostart_var.set(config.get("autostart", False))
                
                self.update_folder_list_ui()
                self.update_button_states()
                self.log_message("Configurações carregadas.")

                if self.autostart_var.get() and self.target_directories:
                    self.start_monitoring()

        except (json.JSONDecodeError, FileNotFoundError) as e:
            self.log_message(f"Nenhum arquivo de configuração encontrado ou está corrompido. Erro: {e}")

    def save_config(self):
        config = {
            "folders": self.target_directories,
            "autostart": self.autostart_var.get()
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)

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
        for widget in self.folder_list_frame.winfo_children():
            widget.destroy()
        for i, folder in enumerate(self.target_directories):
            item_frame = ctk.CTkFrame(self.folder_list_frame)
            item_frame.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
            item_frame.grid_columnconfigure(0, weight=1)
            label = ctk.CTkLabel(item_frame, text=folder, wraplength=550)
            label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
            remove_button = ctk.CTkButton(item_frame, text="Remover", width=80, command=lambda f=folder: self.remove_folder(f))
            remove_button.grid(row=0, column=1, padx=10, pady=5, sticky="e")

    def organize_existing_files(self, directory_to_organize):
        self.log_message(f"Organizando arquivos existentes em: {directory_to_organize}")
        handler = FileOrganizerHandler(directory_to_organize, self)
        try:
            for filename in os.listdir(directory_to_organize):
                file_path = os.path.join(directory_to_organize, filename)
                if os.path.isfile(file_path):
                    handler.process(file_path)
            self.log_message(f"Organização inicial de '{os.path.basename(directory_to_organize)}' concluída.")
        except Exception as e:
            self.log_message(f"Erro na organização inicial: {e}")

    def start_monitoring(self):
        if not self.target_directories:
            messagebox.showwarning("Aviso", "Adicione pelo menos uma pasta para monitorar.")
            return
        if self.is_monitoring:
            return

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
            self.log_message("Monitoramento em tempo real iniciado em todas as pastas.")
            while self.is_monitoring:
                time.sleep(1)
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

    def update_button_states(self):
        has_folders = bool(self.target_directories)
        if self.is_monitoring:
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.add_folder_button.configure(state="disabled")
            self.autostart_checkbox.configure(state="disabled")
            for item_frame in self.folder_list_frame.winfo_children():
                item_frame.winfo_children()[1].configure(state="disabled")
        else:
            self.start_button.configure(state="normal" if has_folders else "disabled")
            self.stop_button.configure(state="disabled")
            self.add_folder_button.configure(state="normal")
            self.autostart_checkbox.configure(state="normal")
            for item_frame in self.folder_list_frame.winfo_children():
                item_frame.winfo_children()[1].configure(state="normal")

    def log_message(self, message):
        def _update_log():
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", f"{message}\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
        self.after(0, _update_log)

if __name__ == "__main__":
    # É necessário instalar as bibliotecas: pip install pystray Pillow
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()