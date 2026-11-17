"""
AudioBridge - Modern GUI (Figma Design)
File queue, waveform preview, settings sidebar
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
import subprocess

from converter import AudioConverter, AudioInspector

# Lazy import for analysis modules
try:
    from converter import AudioAnalyzer
    ANALYSIS_AVAILABLE = True
except ImportError:
    ANALYSIS_AVAILABLE = False


class AudioBridgeGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AudioBridge v2.0")
        self.root.geometry("1200x700")
        
        # Dark theme colors matching Figma
        self.colors = {
            'bg': '#0d1117',
            'surface': '#161b22',
            'border': '#30363d',
            'text': '#c9d1d9',
            'text_dim': '#8b949e',
            'accent': '#58a6ff',
            'accent_hover': '#1f6feb',
            'success': '#238636',
            'card': '#21262d'
        }
        
        self.root.configure(bg=self.colors['bg'])

        try:
            self.converter = AudioConverter()
            self.inspector = AudioInspector()
            self.analyzer = AudioAnalyzer() if ANALYSIS_AVAILABLE else None
        except RuntimeError as e:
            messagebox.showerror("Error", f"FFmpeg not found: {e}")
            self.root.destroy()
            return

        self.file_queue = []
        self.output_dir = None
        self.converting = False
        self.selected_file = None

        self._build_ui()

    def _build_ui(self):
        # Main container with 3 columns
        main_container = tk.Frame(self.root, bg=self.colors['bg'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Left column - File Queue
        self._build_file_queue(main_container)

        # Center column - Preview
        self._build_preview_section(main_container)

        # Right column - Settings
        self._build_settings_panel(main_container)

    def _build_file_queue(self, parent):
        frame = tk.Frame(parent, bg=self.colors['surface'], padx=15, pady=15)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # Header
        header = tk.Label(
            frame, 
            text="Conversion Studio", 
            font=('Segoe UI', 14, 'bold'),
            bg=self.colors['surface'],
            fg=self.colors['text']
        )
        header.pack(anchor=tk.W, pady=(0, 15))

        # Upload button
        upload_btn = tk.Button(
            frame,
            text="+ Upload Audio Files",
            command=self._upload_files,
            font=('Segoe UI', 11),
            bg=self.colors['accent'],
            fg='white',
            activebackground=self.colors['accent_hover'],
            activeforeground='white',
            relief=tk.FLAT,
            padx=20,
            pady=10,
            cursor='hand2'
        )
        upload_btn.pack(fill=tk.X, pady=(0, 15))

        # File list
        list_frame = tk.Frame(frame, bg=self.colors['card'])
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.file_listbox = tk.Listbox(
            list_frame,
            bg=self.colors['bg'],
            fg=self.colors['text'],
            font=('Segoe UI', 10),
            selectbackground=self.colors['accent'],
            selectforeground='white',
            borderwidth=0,
            highlightthickness=0
        )
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.file_listbox.bind('<<ListboxSelect>>', self._on_file_select)

    def _build_preview_section(self, parent):
        frame = tk.Frame(parent, bg=self.colors['surface'], padx=15, pady=15)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # Header
        header = tk.Label(
            frame, 
            text="Preview", 
            font=('Segoe UI', 14, 'bold'),
            bg=self.colors['surface'],
            fg=self.colors['text']
        )
        header.pack(anchor=tk.W, pady=(0, 15))

        # Waveform area
        self.waveform_frame = tk.Frame(frame, bg=self.colors['card'], height=250)
        self.waveform_frame.pack(fill=tk.X, pady=(0, 15))
        self.waveform_frame.pack_propagate(False)

        self.waveform_label = tk.Label(
            self.waveform_frame,
            text="Select a file to preview",
            font=('Segoe UI', 10),
            bg=self.colors['card'],
            fg=self.colors['text_dim']
        )
        self.waveform_label.pack(expand=True)

        # File info
        self.info_frame = tk.Frame(frame, bg=self.colors['card'], padx=15, pady=15)
        self.info_frame.pack(fill=tk.X, pady=(0, 15))

        self.info_label = tk.Label(
            self.info_frame,
            text="No file selected",
            font=('Segoe UI', 10),
            bg=self.colors['card'],
            fg=self.colors['text_dim'],
            justify=tk.LEFT
        )
        self.info_label.pack(anchor=tk.W)

        # Output folder
        output_frame = tk.Frame(frame, bg=self.colors['card'], padx=15, pady=15)
        output_frame.pack(fill=tk.X)

        tk.Label(
            output_frame,
            text="Output Folder",
            font=('Segoe UI', 10, 'bold'),
            bg=self.colors['card'],
            fg=self.colors['text']
        ).pack(anchor=tk.W, pady=(0, 8))

        self.output_label = tk.Label(
            output_frame,
            text="Not selected",
            font=('Segoe UI', 10),
            bg=self.colors['card'],
            fg=self.colors['text_dim']
        )
        self.output_label.pack(anchor=tk.W, pady=(0, 8))

        tk.Button(
            output_frame,
            text="Browse",
            command=self._select_output_dir,
            font=('Segoe UI', 9),
            bg=self.colors['surface'],
            fg=self.colors['text'],
            activebackground=self.colors['border'],
            relief=tk.FLAT,
            padx=15,
            pady=5,
            cursor='hand2'
        ).pack(anchor=tk.W)

    def _build_settings_panel(self, parent):
        frame = tk.Frame(parent, bg=self.colors['surface'], padx=15, pady=15, width=280)
        frame.pack(side=tk.LEFT, fill=tk.Y)
        frame.pack_propagate(False)

        # Header
        header = tk.Label(
            frame, 
            text="Conversion Settings", 
            font=('Segoe UI', 14, 'bold'),
            bg=self.colors['surface'],
            fg=self.colors['text']
        )
        header.pack(anchor=tk.W, pady=(0, 20))

        # Output format
        self._build_setting_row(frame, "Output Format", ["WAV"], "WAV")
        
        # Sample rate
        self._build_setting_row(frame, "Sample Rate", ["Keep Original", "16000 Hz", "22050 Hz", "44100 Hz"], "Keep Original")
        
        # Bit depth
        self._build_setting_row(frame, "Bit Depth", ["16-bit", "24-bit"], "16-bit")
        
        # Channels
        self._build_setting_row(frame, "Channels", ["Keep Original", "Mono", "Stereo"], "Keep Original")

        # Convert button
        convert_btn = tk.Button(
            frame,
            text="Convert All",
            command=self._start_conversion,
            font=('Segoe UI', 11, 'bold'),
            bg=self.colors['success'],
            fg='white',
            activebackground='#2ea043',
            activeforeground='white',
            relief=tk.FLAT,
            padx=20,
            pady=12,
            cursor='hand2'
        )
        convert_btn.pack(fill=tk.X, pady=(30, 0))

        # Progress
        self.progress = ttk.Progressbar(frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(15, 5))

        self.status_label = tk.Label(
            frame,
            text="Ready",
            font=('Segoe UI', 9),
            bg=self.colors['surface'],
            fg=self.colors['text_dim']
        )
        self.status_label.pack(anchor=tk.W)

    def _build_setting_row(self, parent, label, options, default):
        row = tk.Frame(parent, bg=self.colors['surface'])
        row.pack(fill=tk.X, pady=(0, 15))

        tk.Label(
            row,
            text=label,
            font=('Segoe UI', 10),
            bg=self.colors['surface'],
            fg=self.colors['text']
        ).pack(anchor=tk.W, pady=(0, 5))

        setting_var = tk.StringVar(value=default)
        self.__setattr__(f"{label.lower().replace(' ', '_')}_var", setting_var)

        for opt in options:
            rb = tk.Radiobutton(
                row,
                text=opt,
                variable=setting_var,
                value=opt,
                font=('Segoe UI', 9),
                bg=self.colors['surface'],
                fg=self.colors['text'],
                selectcolor=self.colors['accent'],
                activebackground=self.colors['surface'],
                activeforeground=self.colors['text'],
                cursor='hand2'
            )
            rb.pack(anchor=tk.W)

    def _upload_files(self):
        files = filedialog.askopenfilenames(title="Select Audio/Video Files")
        if files:
            for file in files:
                self.file_queue.append(file)
                self.file_listbox.insert(tk.END, Path(file).name)

    def _on_file_select(self, event):
        selection = self.file_listbox.curselection()
        if selection:
            index = selection[0]
            self.selected_file = Path(self.file_queue[index])
            self._update_preview()

    def _update_preview(self):
        if not self.selected_file:
            return

        # Update info
        try:
            metadata = self.inspector.inspect(self.selected_file)
            info = f"File: {self.selected_file.name}\n"
            info += f"Duration: {metadata.get('duration', 'N/A'):.2f}s\n"
            info += f"Sample Rate: {metadata.get('sample_rate', 'N/A')} Hz\n"
            info += f"Channels: {metadata.get('channels', 'N/A')}\n"
            info += f"Codec: {metadata.get('codec', 'N/A')}"
            self.info_label.config(text=info, fg=self.colors['text'])
        except:
            self.info_label.config(text="Could not read file info", fg=self.colors['text_dim'])

        # Show waveform
        self._show_waveform_in_frame()

    def _show_waveform_in_frame(self):
        try:
            import matplotlib.pyplot as plt
            import numpy as np
            import soundfile as sf
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except ImportError:
            self.waveform_label.config(text="Waveform requires matplotlib\nInstall: pip install matplotlib numpy")
            return

        try:
            data, sr = sf.read(str(self.selected_file))
            
            # Clear previous
            for widget in self.waveform_frame.winfo_children():
                widget.destroy()

            # Create matplotlib figure
            fig, ax = plt.subplots(figsize=(5, 2.5), dpi=100)
            fig.patch.set_facecolor(self.colors['card'])
            ax.set_facecolor(self.colors['card'])
            
            # Plot waveform
            ax.plot(np.arange(len(data)) / sr, data, color=self.colors['accent'], linewidth=0.5)
            ax.set_xlabel('Time (s)', color=self.colors['text_dim'], fontsize=8)
            ax.set_ylabel('Amplitude', color=self.colors['text_dim'], fontsize=8)
            ax.tick_params(colors=self.colors['text_dim'], labelsize=8)
            ax.spines['bottom'].set_color(self.colors['border'])
            ax.spines['top'].set_color(self.colors['border'])
            ax.spines['left'].set_color(self.colors['border'])
            ax.spines['right'].set_color(self.colors['border'])
            ax.set_title(self.selected_file.name, color=self.colors['text'], fontsize=10, fontweight='bold')
            
            plt.tight_layout()

            # Embed in tkinter
            canvas = FigureCanvasTkAgg(fig, master=self.waveform_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        except Exception as e:
            self.waveform_label.config(text=f"Error: {str(e)}", fg=self.colors['text_dim'])

    def _select_output_dir(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir = Path(directory)
            self.output_label.config(text=str(self.output_dir), fg=self.colors['text'])

    def _start_conversion(self):
        if not self.file_queue:
            messagebox.showwarning("Warning", "Please upload files first")
            return

        if not self.output_dir:
            messagebox.showwarning("Warning", "Please select output folder")
            return

        self.converting = True
        thread = threading.Thread(target=self._run_conversion)
        thread.daemon = True
        thread.start()

    def _run_conversion(self):
        # Parse settings
        sample_rate_map = {
            "Keep Original": None,
            "16000 Hz": 16000,
            "22050 Hz": 22050,
            "44100 Hz": 44100
        }
        bit_depth_map = {"16-bit": 16, "24-bit": 24}
        channels_map = {
            "Keep Original": False,
            "Mono": True,
            "Stereo": False
        }

        sample_rate = sample_rate_map.get(self.sample_rate_var.get())
        bit_depth = bit_depth_map.get(self.bit_depth_var.get())
        mono = channels_map.get(self.channels_var.get())

        def progress_callback(current, total, file_path, result):
            self.root.after(0, self._update_progress, current, total, file_path, result)

        batch_result = self.converter.batch_convert(self.file_queue, self.output_dir, sample_rate=sample_rate, mono=mono, bit_depth=bit_depth, progress_callback=progress_callback)
        self.root.after(0, self._conversion_complete, batch_result)

    def _update_progress(self, current, total, file_path, result):
        self.progress['value'] = (current / total) * 100
        self.status_label.config(text=f"Converting {current}/{total}")

    def _conversion_complete(self, batch_result):
        self.converting = False
        self.status_label.config(text=f"Complete: {batch_result['successful']} successful, {batch_result['failed']} failed")
        messagebox.showinfo("Complete", f"Converted {batch_result['successful']} files successfully")


def main():
    root = tk.Tk()
    app = AudioBridgeGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
