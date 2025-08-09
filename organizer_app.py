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
from datetime import datetime
from collections import deque

# Importações específicas para Windows
import sys
if sys.platform == 'win32':
    import win32com.client
    import pythoncom
    # Novas importações para a verificação de instância única
    import win32event
    import win32api
    from winerror import ERROR_ALREADY_EXISTS
    import win32gui

# --- Constantes e Configurações Padrão ---
CONFIG_FILE = "config.json"
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
HISTORY_LIMIT = 100 # Limite de ações no histórico para a função "Desfazer"
# Lista de extensões temporárias a serem ignoradas para evitar erros de download
TEMP_EXTENSIONS = {'.tmp', '.crdownload', '.part'}

class FileOrganizerHandler(FileSystemEventHandler):
    """Manipula os eventos do sistema de ficheiros."""
    def __init__(self, watch_directory, app_instance):
        self.watch_directory = watch_directory
        self.app = app_instance

    def on_created(self, event):
        if not event.is_directory:
            # Adiciona uma verificação mais robusta para garantir que o ficheiro está completo
            self.wait_for_file_to_be_ready(event.src_path)

    def wait_for_file_to_be_ready(self, file_path):
        """Espera até que um ficheiro não esteja mais a ser modificado antes de o processar."""
        try:
            if not os.path.exists(file_path):
                return

            # Ignora imediatamente ficheiros temporários conhecidos
            _, file_extension = os.path.splitext(file_path)
            if file_extension.lower() in TEMP_EXTENSIONS:
                return

            # Espera até que o tamanho do ficheiro se estabilize
            last_size = -1
            stable_count = 0
            max_stable_count = 3  # Requer 3 segundos de estabilidade

            while stable_count < max_stable_count:
                if not os.path.exists(file_path):
                    return # O ficheiro foi removido durante a verificação

                current_size = os.path.getsize(file_path)
                if current_size == last_size and current_size != 0:
                    stable_count += 1
                else:
                    stable_count = 0 # Reinicia a contagem se o tamanho mudar
                
                last_size = current_size
                time.sleep(1)
            
            # Se o ficheiro ainda existir após a espera, processa-o
            if os.path.exists(file_path):
                self.process(file_path)

        except (FileNotFoundError, PermissionError):
            # Ignora erros se o ficheiro for removido ou estiver bloqueado
            pass
        except Exception as e:
            self.app.log_message(f"Erro ao verificar ficheiro '{os.path.basename(file_path)}': {e}")

    def process(self, file_path):
        """Processa e move um único ficheiro com base nas regras definidas."""
        try:
            if not os.path.exists(file_path): return
            filename = os.path.basename(file_path)
            if filename.startswith('.') or filename.startswith('~'): return

            # --- Lógica de Destino ---
            destination_folder_name = None
            
            # 1. Prioridade para Regras por Palavra-Chave
            for keyword, folder in self.app.keyword_rules.items():
                if keyword.lower() in filename.lower():
                    destination_folder_name = folder
                    break
            
            # 2. Se não houver correspondência, usar Regras por Extensão
            if not destination_folder_name:
                _, file_extension = os.path.splitext(filename)
                file_extension = file_extension.lower()
                if file_extension:
                    destination_folder_name = self.app.extension_map.get(file_extension, f"Outros_{file_extension.replace('.', '').upper()}")
            
            if not destination_folder_name:
                return

            # --- Montagem do Caminho Final ---
            final_destination_path = os.path.join(self.watch_directory, destination_folder_name)

            # 3. Adicionar Subpastas por Data, se ativado
            if self.app.organize_by_date_var.get():
                try:
                    mod_time = os.path.getmtime(file_path)
                    date = datetime.fromtimestamp(mod_time)
                    year_folder = str(date.year)
                    month_folder = date.strftime("%m-") + self.app.get_month_name(date.month)
                    final_destination_path = os.path.join(final_destination_path, year_folder, month_folder)
                except Exception as e:
                    self.app.log_message(f"Erro ao obter data de '{filename}': {e}. Organizando sem data.")

            # --- Mover o Ficheiro ---
            destination_file_path = os.path.join(final_destination_path, filename)

            if os.path.normpath(file_path) == os.path.normpath(destination_file_path):
                return

            if not os.path.exists(final_destination_path):
                os.makedirs(final_destination_path)
            
            shutil.move(file_path, destination_file_path)

            # --- Registar Ação ---
            log_msg = f"'{filename}' movido para '{os.path.relpath(final_destination_path, self.watch_directory)}'."
            self.app.log_message(log_msg)
            self.app.add_to_history(file_path, destination_file_path, log_msg)

        except Exception as e:
            self.app.log_message(f"ERRO ao processar '{filename}': {e}")

class App(ctk.CTk):
    def __init__(self, start_minimized=False):
        super().__init__()
        self.title("Organizador de Ficheiros Automático")
        self.geometry("850x750")

        # --- Variáveis de Estado ---
        self.target_directories = []
        self.extension_map = {}
        self.keyword_rules = {}
        self.move_history = deque(maxlen=HISTORY_LIMIT)
        self.observers = []
        self.monitoring_thread = None
        self.is_monitoring = False
        self.autostart_var = tk.BooleanVar()
        self.startup_var = tk.BooleanVar()
        self.organize_by_date_var = tk.BooleanVar()
        self.tray_icon = None
        self.sub_window = None
        self.mutex = None # Variável para guardar o handle do mutex
        self.extension_list_frame = None
        self.keyword_list_frame = None

        self.create_widgets()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        if start_minimized:
            self.after(100, self.hide_window)

    def create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sistema de Abas ---
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="nsew")
        self.tab_view.add("Principal")
        self.tab_view.add("Regras de Extensão")
        self.tab_view.add("Regras de Palavra-Chave")
        self.tab_view.add("Histórico")

        # --- Aba Principal ---
        self.setup_main_tab()
        # --- Aba de Extensões ---
        self.setup_rules_tab(self.tab_view.tab("Regras de Extensão"), "Extensão", self.extension_map, self.add_extension_rule, self.remove_extension_rule)
        # --- Aba de Palavras-Chave ---
        self.setup_rules_tab(self.tab_view.tab("Regras de Palavra-Chave"), "Palavra-Chave", self.keyword_rules, self.add_keyword_rule, self.remove_keyword_rule)
        # --- Aba de Histórico ---
        self.setup_history_tab()
        
        # --- Rodapé ---
        current_year = datetime.now().year
        footer_label = ctk.CTkLabel(self, text=f"© {current_year} Rafael Custódio. Todos os direitos reservados.", font=ctk.CTkFont(size=10), text_color="gray")
        footer_label.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="s")


    def setup_main_tab(self):
        tab = self.tab_view.tab("Principal")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1) # Lista de pastas
        tab.grid_rowconfigure(3, weight=1) # Log

        # Controles de Pastas
        folder_controls_frame = ctk.CTkFrame(tab)
        folder_controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        folder_controls_frame.grid_columnconfigure((0, 1), weight=1)
        self.add_folder_button = ctk.CTkButton(folder_controls_frame, text="Adicionar Pasta para Monitorizar", command=self.add_folder)
        self.add_folder_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.create_safe_folder_button = ctk.CTkButton(folder_controls_frame, text="Criar Pasta Segura", command=self.create_safe_folder)
        self.create_safe_folder_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Lista de Pastas
        self.folder_list_frame = ctk.CTkScrollableFrame(tab, label_text="Pastas Monitorizadas (só a raiz de cada pasta é monitorizada em tempo real)")
        self.folder_list_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.folder_list_frame.grid_columnconfigure(0, weight=1)

        # Controles Gerais
        general_controls_frame = ctk.CTkFrame(tab)
        general_controls_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        general_controls_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.start_button = ctk.CTkButton(general_controls_frame, text="Iniciar Monitorização", command=self.start_monitoring)
        self.start_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.stop_button = ctk.CTkButton(general_controls_frame, text="Parar Monitorização", command=self.stop_monitoring)
        self.stop_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.undo_button = ctk.CTkButton(general_controls_frame, text="Desfazer Última Ação", command=self.undo_last_move)
        self.undo_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # Checkboxes de Configuração
        checkbox_frame = ctk.CTkFrame(tab)
        checkbox_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew")
        self.autostart_checkbox = ctk.CTkCheckBox(checkbox_frame, text="Iniciar monitorização ao abrir o programa", variable=self.autostart_var, command=self.save_config)
        self.autostart_checkbox.pack(anchor="w", padx=10, pady=5)
        self.organize_by_date_var_checkbox = ctk.CTkCheckBox(checkbox_frame, text="Criar subpastas por Ano/Mês", variable=self.organize_by_date_var, command=self.save_config)
        self.organize_by_date_var_checkbox.pack(anchor="w", padx=10, pady=5)
        self.startup_checkbox = ctk.CTkCheckBox(checkbox_frame, text="Iniciar com o Windows (minimizado na bandeja)", variable=self.startup_var, command=self.toggle_startup)
        self.startup_checkbox.pack(anchor="w", padx=10, pady=5)
        if sys.platform != 'win32':
            self.startup_checkbox.configure(state="disabled", text="Iniciar com o Windows (Apenas no Windows)")

        # Log
        self.log_textbox = ctk.CTkTextbox(tab, state="disabled", wrap="word")
        self.log_textbox.grid(row=4, column=0, padx=10, pady=10, sticky="nsew")

    def setup_rules_tab(self, tab, rule_type, data_dict, add_command, remove_command):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        add_frame = ctk.CTkFrame(tab)
        add_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        key_placeholder = ".ext" if rule_type == "Extensão" else "Palavra-chave"
        key_entry = ctk.CTkEntry(add_frame, placeholder_text=key_placeholder)
        key_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        folder_entry = ctk.CTkEntry(add_frame, placeholder_text="Nome da Pasta de Destino")
        folder_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        add_button = ctk.CTkButton(add_frame, text="Adicionar", width=80, command=lambda: add_command(key_entry.get(), folder_entry.get(), key_entry, folder_entry))
        add_button.pack(side="left", padx=5, pady=5)
        
        # Botão para restaurar padrões
        if rule_type == "Extensão":
            restore_button = ctk.CTkButton(add_frame, text="Restaurar Padrões", command=self.restore_default_extensions)
            restore_button.pack(side="left", padx=(5, 10), pady=5)

        list_frame = ctk.CTkScrollableFrame(tab, label_text=f"Regras de {rule_type}")
        list_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        if rule_type == "Extensão":
            self.extension_list_frame = list_frame
        elif rule_type == "Palavra-Chave":
            self.keyword_list_frame = list_frame
            
        self.populate_rules_list(list_frame, data_dict, remove_command)

    def setup_history_tab(self):
        tab = self.tab_view.tab("Histórico")
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        self.history_list_frame = ctk.CTkScrollableFrame(tab, label_text="Últimas Ações Realizadas")
        self.history_list_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.history_list_frame.grid_columnconfigure(0, weight=1)

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.target_directories = config.get("folders", [])
                self.autostart_var.set(config.get("autostart", False))
                self.organize_by_date_var.set(config.get("organize_by_date", False))
                self.extension_map = config.get("extensions", DEFAULT_EXTENSION_MAP.copy())
                self.keyword_rules = config.get("keyword_rules", {})
                self.move_history = deque(config.get("move_history", []), maxlen=HISTORY_LIMIT)
                self.log_message("Configurações carregadas.")
            else:
                self.extension_map = DEFAULT_EXTENSION_MAP.copy()
                self.log_message("Nenhum ficheiro de configuração encontrado. Usando padrões.")

            if sys.platform == 'win32': self.startup_var.set(self.check_if_startup_shortcut_exists())
            self.update_all_ui_parts()
            if self.autostart_var.get() and self.target_directories: self.start_monitoring()
        except Exception as e:
            self.log_message(f"Erro ao carregar config: {e}")
            self.extension_map = DEFAULT_EXTENSION_MAP.copy()

    def save_config(self):
        config = {
            "folders": self.target_directories,
            "autostart": self.autostart_var.get(),
            "organize_by_date": self.organize_by_date_var.get(),
            "extensions": self.extension_map,
            "keyword_rules": self.keyword_rules,
            "move_history": list(self.move_history)
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        self.log_message("Configurações salvas.")

    def populate_rules_list(self, list_frame, data_dict, remove_command):
        for widget in list_frame.winfo_children(): widget.destroy()
        sorted_rules = sorted(data_dict.items())
        for key, folder in sorted_rules:
            item_frame = ctk.CTkFrame(list_frame)
            item_frame.pack(fill="x", padx=5, pady=2)
            item_frame.grid_columnconfigure(0, weight=1)
            label = ctk.CTkLabel(item_frame, text=f"'{key}'  ->  '{folder}'", font=ctk.CTkFont(family="monospace"))
            label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
            remove_button = ctk.CTkButton(item_frame, text="Remover", width=80, fg_color="red", hover_color="darkred", command=lambda k=key: remove_command(k))
            remove_button.grid(row=0, column=1, padx=10, pady=5, sticky="e")

    def add_extension_rule(self, ext, folder, key_entry, folder_entry):
        if not ext or not folder: return
        if not ext.startswith('.'): ext = '.' + ext
        self.extension_map[ext.lower()] = folder
        self.save_config()
        self.update_rules_tab_ui("Regras de Extensão")
        key_entry.delete(0, "end"); folder_entry.delete(0, "end")
        self.prompt_for_rescan()

    def remove_extension_rule(self, ext):
        if ext in self.extension_map:
            del self.extension_map[ext]
            self.save_config()
            self.update_rules_tab_ui("Regras de Extensão")

    def add_keyword_rule(self, keyword, folder, key_entry, folder_entry):
        if not keyword or not folder: return
        self.keyword_rules[keyword] = folder
        self.save_config()
        self.update_rules_tab_ui("Regras de Palavra-Chave")
        key_entry.delete(0, "end"); folder_entry.delete(0, "end")
        self.prompt_for_rescan()

    def remove_keyword_rule(self, keyword):
        if keyword in self.keyword_rules:
            del self.keyword_rules[keyword]
            self.save_config()
            self.update_rules_tab_ui("Regras de Palavra-Chave")
            
    def restore_default_extensions(self):
        if messagebox.askyesno("Restaurar Regras Padrão?",
                               "Tem a certeza de que deseja apagar todas as suas regras de extensão personalizadas e restaurar a lista padrão?",
                               parent=self):
            self.extension_map = DEFAULT_EXTENSION_MAP.copy()
            self.save_config()
            self.update_rules_tab_ui("Regras de Extensão")
            self.log_message("Regras de extensão restauradas para o padrão.")

    def prompt_for_rescan(self):
        """Pergunta ao utilizador se deseja fazer uma nova verificação após adicionar uma regra."""
        if self.is_monitoring:
            if messagebox.askyesno("Aplicar Nova Regra?", 
                                   "A monitorização está ativa. Deseja verificar novamente as pastas para aplicar esta nova regra aos ficheiros existentes?",
                                   parent=self):
                self.rescan_folders()

    def rescan_folders(self):
        """Inicia uma nova verificação de todas as pastas monitorizadas numa thread separada."""
        if not self.is_monitoring:
            return

        self.log_message("Iniciando nova verificação para aplicar novas regras...")
        
        def rescan_task():
            for directory in self.target_directories:
                if not self.is_monitoring:
                    self.log_message("Nova verificação cancelada.")
                    break
                self.organize_existing_files(directory)
            
            if self.is_monitoring:
                self.log_message("Nova verificação concluída.")

        threading.Thread(target=rescan_task, daemon=True).start()

    def add_to_history(self, source, destination, log_msg):
        self.move_history.append({"source": source, "destination": destination, "log_msg": log_msg})
        self.update_history_tab_ui()
        self.update_button_states()
        self.save_config()

    def undo_last_move(self):
        if not self.move_history:
            self.log_message("Nenhuma ação para desfazer.")
            return
        last_action = self.move_history.pop()
        source_path_original = last_action["source"]
        dest_path = last_action["destination"]
        try:
            source_dir = os.path.dirname(source_path_original)
            if not os.path.exists(source_dir):
                os.makedirs(source_dir)
            
            shutil.move(dest_path, source_path_original)
            self.log_message(f"DESFEITO: '{os.path.basename(source_path_original)}' retornado para sua origem.")
            self.update_history_tab_ui()
            self.save_config()
        except Exception as e:
            self.log_message(f"ERRO ao desfazer: {e}")
            self.move_history.append(last_action)
        self.update_button_states()

    def update_all_ui_parts(self):
        self.update_folder_list_ui()
        self.update_rules_tab_ui("Regras de Extensão")
        self.update_rules_tab_ui("Regras de Palavra-Chave")
        self.update_history_tab_ui()
        self.update_button_states()

    def update_folder_list_ui(self):
        for widget in self.folder_list_frame.winfo_children(): widget.destroy()
        for folder in self.target_directories:
            item_frame = ctk.CTkFrame(self.folder_list_frame)
            item_frame.pack(fill="x", padx=5, pady=2)
            item_frame.grid_columnconfigure(0, weight=1)
            label = ctk.CTkLabel(item_frame, text=folder, wraplength=600)
            label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
            remove_button = ctk.CTkButton(item_frame, text="Remover", width=80, command=lambda f=folder: self.remove_folder(f))
            remove_button.grid(row=0, column=1, padx=10, pady=5, sticky="e")

    def update_rules_tab_ui(self, tab_name):
        if tab_name == "Regras de Extensão" and self.extension_list_frame:
            self.populate_rules_list(self.extension_list_frame, self.extension_map, self.remove_extension_rule)
        elif tab_name == "Regras de Palavra-Chave" and self.keyword_list_frame:
            self.populate_rules_list(self.keyword_list_frame, self.keyword_rules, self.remove_keyword_rule)

    def update_history_tab_ui(self):
        for widget in self.history_list_frame.winfo_children(): widget.destroy()
        for action in reversed(self.move_history):
            label = ctk.CTkLabel(self.history_list_frame, text=action["log_msg"], wraplength=700, justify="left")
            label.pack(anchor="w", padx=10, pady=2)

    def update_button_states(self):
        is_monitoring = self.is_monitoring
        has_folders = bool(self.target_directories)
        has_history = bool(self.move_history)

        self.start_button.configure(state="normal" if not is_monitoring and has_folders else "disabled")
        self.stop_button.configure(state="normal" if is_monitoring else "disabled")
        self.undo_button.configure(state="normal" if not is_monitoring and has_history else "disabled")
        self.add_folder_button.configure(state="normal" if not is_monitoring else "disabled")
        self.create_safe_folder_button.configure(state="normal" if not is_monitoring and has_folders else "disabled")
        
        self.autostart_checkbox.configure(state="normal" if not is_monitoring else "disabled")
        self.organize_by_date_var_checkbox.configure(state="normal" if not is_monitoring else "disabled")
        if sys.platform == 'win32': self.startup_checkbox.configure(state="normal" if not is_monitoring else "disabled")

        for item_frame in self.folder_list_frame.winfo_children():
            item_frame.winfo_children()[1].configure(state="normal" if not is_monitoring else "disabled")
    
    def start_monitoring(self):
        if not self.target_directories: return
        if self.is_monitoring: return
        self.is_monitoring = True
        self.update_button_states()
        def monitor_task():
            self.observers = []
            for directory in self.target_directories:
                self.organize_existing_files(directory)
                if not self.is_monitoring: break
                event_handler = FileOrganizerHandler(directory, self)
                observer = Observer()
                observer.schedule(event_handler, directory, recursive=False)
                observer.start()
                self.observers.append(observer)
            
            if self.is_monitoring:
                self.log_message("Monitorização em tempo real iniciada.")

            while self.is_monitoring: time.sleep(1)

            for observer in self.observers:
                observer.stop(); observer.join()
            self.log_message("Monitorização parada.")
        self.monitoring_thread = threading.Thread(target=monitor_task, daemon=True)
        self.monitoring_thread.start()

    def stop_monitoring(self):
        if self.is_monitoring:
            self.log_message("A parar a monitorização... Por favor, aguarde.")
            self.is_monitoring = False
            self.update_button_states()
    
    def organize_existing_files(self, directory):
        self.log_message(f"Verificando ficheiros na raiz de: {os.path.basename(directory)}")
        handler = FileOrganizerHandler(directory, self)
        try:
            for filename in os.listdir(directory):
                if not self.is_monitoring:
                    self.log_message("A verificação inicial foi cancelada pelo utilizador.")
                    return
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    handler.process(file_path)
        except Exception as e:
            self.log_message(f"Erro na varredura inicial: {e}")

    def get_month_name(self, month_number):
        months = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        return months[month_number - 1]

    def add_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected and folder_selected not in self.target_directories:
            self.target_directories.append(folder_selected)
            self.update_all_ui_parts()
            self.save_config()

    def remove_folder(self, folder_to_remove):
        self.target_directories.remove(folder_to_remove)
        self.update_all_ui_parts()
        self.save_config()
        
    def create_safe_folder(self):
        initial_dir = self.target_directories[0] if self.target_directories else os.path.expanduser("~")
        parent_folder = filedialog.askdirectory(
            title="Selecione onde criar a Pasta Segura",
            initialdir=initial_dir,
            parent=self
        )
        
        if not parent_folder:
            return

        dialog = ctk.CTkInputDialog(text="Digite o nome da nova pasta segura:", title="Criar Pasta Segura")
        folder_name = dialog.get_input()
        
        if folder_name:
            try:
                safe_folder_path = os.path.join(parent_folder, folder_name)
                if not os.path.exists(safe_folder_path):
                    os.makedirs(safe_folder_path)
                    self.log_message(f"Pasta segura '{folder_name}' criada em '{parent_folder}'.")
                else:
                    self.log_message(f"A pasta '{folder_name}' já existe em '{parent_folder}'.")
            except Exception as e:
                self.log_message(f"Erro ao criar pasta segura: {e}")


    def log_message(self, message):
        def _update_log():
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
        self.after(0, _update_log)

    def toggle_startup(self):
        if sys.platform != 'win32': return
        shortcut_path = self.get_shortcut_path()
        executable_path = sys.executable
        try:
            if self.startup_var.get():
                pythoncom.CoInitialize()
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.TargetPath = executable_path
                shortcut.Arguments = "--start-minimized"
                shortcut.WorkingDirectory = os.path.dirname(executable_path)
                shortcut.IconLocation = executable_path
                shortcut.save()
                pythoncom.CoUninitialize()
                self.log_message("Configurado para iniciar com o Windows.")
            else:
                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)
                    self.log_message("Removido da inicialização do Windows.")
        except Exception as e:
            self.log_message(f"Erro ao configurar inicialização: {e}")
            messagebox.showerror("Erro", f"Ocorreu um erro: {e}\nTente executar como administrador.")
            self.startup_var.set(not self.startup_var.get())
    
    def get_startup_folder_path(self):
        return os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')

    def get_shortcut_path(self):
        return os.path.join(self.get_startup_folder_path(), "OrganizadorDeFicheiros.lnk")

    def check_if_startup_shortcut_exists(self):
        return os.path.exists(self.get_shortcut_path())

    def create_tray_image(self):
        width, height, color1, color2 = 64, 64, (20, 20, 120), (100, 180, 255)
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle((width // 4, height // 4, width * 3 // 4, height * 3 // 4), fill=color2)
        return image

    def setup_tray_icon(self):
        icon_image = self.create_tray_image()
        menu = pystray.Menu(pystray.MenuItem('Mostrar', self.show_window, default=True), pystray.MenuItem('Sair', self.quit_app))
        self.tray_icon = pystray.Icon("organizador", icon_image, "Organizador de Ficheiros", menu)
        self.tray_icon.run()

    def hide_window(self):
        self.withdraw()
        threading.Thread(target=self.setup_tray_icon, daemon=True).start()

    def show_window(self):
        if self.tray_icon: self.tray_icon.stop()
        self.deiconify()

    def quit_app(self):
        self.save_config()
        if self.tray_icon: self.tray_icon.stop()
        if self.is_monitoring:
            self.stop_monitoring()
            if self.monitoring_thread: self.monitoring_thread.join(timeout=2)
        self.destroy()

if __name__ == "__main__":
    mutex = None
    if sys.platform == 'win32':
        mutex_name = "OrganizadorDeFicheiros_Global_Mutex_e9a7e6a0-9b1a-4b7c-9c2b-6d6f8a9d0a1b"
        mutex = win32event.CreateMutex(None, 1, mutex_name)
        if win32api.GetLastError() == ERROR_ALREADY_EXISTS:
            hwnd = win32gui.FindWindow(None, "Organizador de Ficheiros Automático")
            if hwnd:
                win32gui.ShowWindow(hwnd, 9)
                win32gui.SetForegroundWindow(hwnd)
            os._exit(0)

    start_minimized_arg = '--start-minimized' in sys.argv
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = App(start_minimized=start_minimized_arg)
    
    if sys.platform == 'win32':
        app.mutex = mutex

    app.mainloop()