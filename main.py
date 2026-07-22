import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from datetime import datetime
from viewmodel import PhotoCopyViewModel

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class PhotoCopyView(ctk.CTk):
    def __init__(self, viewModel):
        super().__init__()
        self.vm = viewModel

        self.title("Advanced Photo Copy Tool - MVVM Architecture")
        self.geometry("780x760") 
        self.resizable(False, False)

        if getattr(sys, 'frozen', False):
            self.wm_iconbitmap(sys.executable)
        else:
            icon_path = os.path.abspath("app_icon.ico")
            if os.path.exists(icon_path):
                self.wm_iconbitmap(icon_path)

        # Nạp cấu hình đã lưu
        saved_config = self.vm.load_saved_config()
        self.input_dir = tk.StringVar(value=saved_config["input_dir"])
        self.output_dir = tk.StringVar(value=saved_config["output_dir"])
        self.chk_original_var = tk.BooleanVar(value=True) 
        self.chk_processed_var = tk.BooleanVar(value=False)
        self.chk_preprocess_var = tk.BooleanVar(value=True) 
        
        # Biến cấu hình CLAHE
        self.clahe_clip_var = tk.StringVar(value=saved_config["clahe_clip"])
        self.clahe_tile_var = tk.StringVar(value=saved_config["clahe_tile"])

        self.setup_ui()
        self.vm.set_callbacks(self.update_log_ui, self.update_progress_ui, self.update_controls_state_ui)
        
        self.update_log_ui(f"System optimization: Configured to run with {self.vm.optimal_threads} parallel threads.")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        title_lbl = ctk.CTkLabel(self, text="PHOTO COPY TOOL (MVVM)", font=ctk.CTkFont(size=22, weight="bold"))
        title_lbl.pack(pady=15)

        # --- FOLDER SELECTION FRAME ---
        input_frame = ctk.CTkFrame(self)
        input_frame.pack(fill="x", padx=20, pady=5)
        
        input_lbl = ctk.CTkLabel(input_frame, text="Source Folder (Input):", width=160, anchor="w")
        input_lbl.pack(side="left", padx=10, pady=8)
        
        self.input_entry = ctk.CTkEntry(input_frame, textvariable=self.input_dir, width=440)
        self.input_entry.pack(side="left", padx=5, pady=8)
        
        btn_browse_in = ctk.CTkButton(input_frame, text="Browse...", width=80, command=self.browse_input)
        btn_browse_in.pack(side="left", padx=10, pady=8)

        output_frame = ctk.CTkFrame(self)
        output_frame.pack(fill="x", padx=20, pady=5)
        
        output_lbl = ctk.CTkLabel(output_frame, text="Destination Folder (Output):", width=160, anchor="w")
        output_lbl.pack(side="left", padx=10, pady=8)
        
        self.output_entry = ctk.CTkEntry(output_frame, textvariable=self.output_dir, width=440)
        self.output_entry.pack(side="left", padx=5, pady=8)
        
        btn_browse_out = ctk.CTkButton(output_frame, text="Browse...", width=80, command=self.browse_output)
        btn_browse_out.pack(side="left", padx=10, pady=8)

        # --- CONFIGURATION FRAME ---
        config_frame = ctk.CTkFrame(self)
        config_frame.pack(fill="x", padx=20, pady=8)

        option_title = ctk.CTkLabel(config_frame, text="Configuration Options:", font=ctk.CTkFont(weight="bold"))
        option_title.pack(anchor="w", padx=15, pady=(8, 4))

        # Checkboxes quét thư mục
        checkbox_container = ctk.CTkFrame(config_frame, fg_color="transparent")
        checkbox_container.pack(fill="x", padx=10, pady=(0, 5))

        self.chk_original = ctk.CTkCheckBox(checkbox_container, text="Scan 'Original'", variable=self.chk_original_var)
        self.chk_original.pack(side="left", padx=10, pady=5)
        
        self.chk_processed = ctk.CTkCheckBox(checkbox_container, text="Scan 'Processed'", variable=self.chk_processed_var)
        self.chk_processed.pack(side="left", padx=15, pady=5)

        # Divider line nhẹ
        ctk.CTkFrame(config_frame, height=1, fg_color="#3A3A3A").pack(fill="x", padx=15, pady=5)

        # Preprocessing & CLAHE Controls
        self.chk_preprocess = ctk.CTkCheckBox(
            config_frame, 
            text="Apply Robust Preprocessing (Tone Mapping + CLAHE)", 
            variable=self.chk_preprocess_var, 
            fg_color="#2B719E",
            command=self.toggle_clahe_inputs
        )
        self.chk_preprocess.pack(anchor="w", padx=20, pady=(5, 5))

        # Frame chứa riêng tùy chỉnh CLAHE (Sắp xếp hàng ngang gọn gàng)
        self.clahe_frame = ctk.CTkFrame(config_frame, fg_color="#2B2B2B", corner_radius=6)
        self.clahe_frame.pack(fill="x", padx=20, pady=(0, 10))

        # Clip Limit Input
        clip_lbl = ctk.CTkLabel(self.clahe_frame, text="CLAHE Clip Limit:", font=ctk.CTkFont(size=12))
        clip_lbl.pack(side="left", padx=(15, 5), pady=8)
        
        self.clip_entry = ctk.CTkEntry(self.clahe_frame, textvariable=self.clahe_clip_var, width=70, justify="center")
        self.clip_entry.pack(side="left", padx=(0, 25), pady=8)

        # Tile Grid Size Selection
        tile_lbl = ctk.CTkLabel(self.clahe_frame, text="CLAHE Tile Grid:", font=ctk.CTkFont(size=12))
        tile_lbl.pack(side="left", padx=(0, 5), pady=8)

        self.tile_menu = ctk.CTkOptionMenu(
            self.clahe_frame, 
            values=["4x4", "8x8", "16x16", "32x32"], 
            variable=self.clahe_tile_var, 
            width=90
        )
        self.tile_menu.pack(side="left", padx=(0, 15), pady=8)

        # --- CONTROL BUTTONS ---
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(fill="x", padx=20, pady=5)

        self.btn_delete = ctk.CTkButton(control_frame, text="DELETE OUTPUT", font=ctk.CTkFont(size=13, weight="bold"), width=150, height=40, fg_color="#555555", hover_color="#333333", command=self.on_delete_clicked)
        self.btn_delete.pack(side="left", pady=5)

        self.btn_stop = ctk.CTkButton(control_frame, text="STOP", font=ctk.CTkFont(size=13, weight="bold"), width=120, height=40, fg_color="#A83232", hover_color="#7A2424", command=self.vm.request_stop, state="disabled")
        self.btn_stop.pack(side="right", padx=5, pady=5)

        self.btn_run = ctk.CTkButton(control_frame, text="RUN PIPELINE", font=ctk.CTkFont(size=13, weight="bold"), width=150, height=40, fg_color="#1F6AA5", hover_color="#144871", command=self.on_run_clicked)
        self.btn_run.pack(side="right", padx=5, pady=5)

        # --- PROGRESS BAR ---
        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame.pack(fill="x", padx=20, pady=(5, 10))

        self.progress_lbl = ctk.CTkLabel(progress_frame, text="Progress: 0/0 images (0%)", font=ctk.CTkFont(size=12, weight="bold"))
        self.progress_lbl.pack(anchor="w", padx=5, pady=(0, 2))

        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.pack(fill="x", padx=5)
        self.progress_bar.set(0) 

        # --- LOG UI ---
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        log_title = ctk.CTkLabel(log_frame, text="Activity Logs:", font=ctk.CTkFont(size=12))
        log_title.pack(anchor="w", padx=10, pady=(5, 0))

        self.log_text = ctk.CTkTextbox(log_frame, state="disabled", font=("Courier New", 12))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_text.tag_config("warning", foreground="#E6B800") 
        self.log_text.tag_config("error", foreground="#FF4D4D")   

        # Cập nhật trạng thái các ô nhập dựa theo checkbox ban đầu
        self.toggle_clahe_inputs()

    def toggle_clahe_inputs(self):
        """Bật/tắt ô cấu hình CLAHE theo trạng thái chọn Preprocessing"""
        state = "normal" if self.chk_preprocess_var.get() else "disabled"
        self.clip_entry.configure(state=state)
        self.tile_menu.configure(state=state)

    def update_log_ui(self, message, level="info"):
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        level_tag = level.lower() if level.lower() in ["warning", "error"] else None
        self.log_text.insert("end", f"{timestamp}{message}\n", level_tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def update_progress_ui(self, value, text_message):
        self.progress_bar.set(value)
        self.progress_lbl.configure(text=text_message)

    def update_controls_state_ui(self):
        if self.vm.is_running:
            self.btn_run.configure(state="disabled")
            self.btn_delete.configure(state="disabled")
            self.chk_original.configure(state="disabled")
            self.chk_processed.configure(state="disabled")
            self.chk_preprocess.configure(state="disabled") 
            self.clip_entry.configure(state="disabled")
            self.tile_menu.configure(state="disabled")
            self.btn_stop.configure(state="normal" if not self.vm.stop_requested else "disabled")
        else:
            self.btn_run.configure(state="normal")
            self.btn_delete.configure(state="normal")
            self.chk_original.configure(state="normal")
            self.chk_processed.configure(state="normal")
            self.chk_preprocess.configure(state="normal") 
            self.toggle_clahe_inputs()
            self.btn_stop.configure(state="disabled")

    def browse_input(self):
        if self.vm.is_running: return
        path = filedialog.askdirectory()
        if path: self.input_dir.set(path)

    def browse_output(self):
        if self.vm.is_running: return
        path = filedialog.askdirectory()
        if path: self.output_dir.set(path)

    def on_run_clicked(self):
        self.vm.start_copy_pipeline(
            self.input_dir.get(),
            self.output_dir.get(),
            self.chk_original_var.get(),
            self.chk_processed_var.get(),
            self.chk_preprocess_var.get(),
            self.clahe_clip_var.get(),
            self.clahe_tile_var.get()
        )

    def on_delete_clicked(self):
        confirm = messagebox.askyesno(
            "Confirmation Required", 
            "Are you sure you want to delete ALL files inside the selected output directory?\nThis action cannot be undone."
        )
        if confirm:
            self.vm.execute_delete(self.output_dir.get())
    
    def on_closing(self):
        # Lưu lại đường dẫn & cấu hình CLAHE khi tắt ứng dụng
        self.vm.save_config(
            self.input_dir.get(), 
            self.output_dir.get(),
            self.clahe_clip_var.get(),
            self.clahe_tile_var.get()
        )
        self.destroy()

if __name__ == "__main__":
    vm = PhotoCopyViewModel()
    app = PhotoCopyView(vm)
    app.mainloop()