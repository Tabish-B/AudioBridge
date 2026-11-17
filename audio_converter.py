#!/usr/bin/env python3
"""
Audio Conversion Helper - GUI Application

A simple, user-friendly tool for converting audio files to WAV format.
Designed for JRF annotators who need convenient access to audio recordings.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
import subprocess
import platform

from converter import AudioConverter, AudioInspector


class AudioConverterGUI:
    """Main GUI application for audio conversion."""

    def __init__(self, root):
        """Initialize the GUI."""
        self.root = root
        self.root.title("Audio Conversion Helper")
        self.root.geometry("800x700")

        # Initialize converter and inspector
        try:
            self.converter = AudioConverter()
            self.inspector = AudioInspector()
        except RuntimeError as e:
            messagebox.showerror(
                "Error",
                f"FFmpeg not found: {e}\n\nPlease install FFmpeg and try again."
            )
            self.root.destroy()
            return

        # State variables
        self.input_files = []
        self.input_folder = None
        self.output_dir = None
        self.converting = False

        # Build GUI
        self._build_ui()

    def _build_ui(self):
        """Build the user interface."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(7, weight=1)  # Results area

        # Title
        title_label = ttk.Label(
            main_frame,
            text="Audio Conversion Helper",
            font=("Helvetica", 16, "bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 5), sticky=tk.W)

        # Important notice
        notice_label = ttk.Label(
            main_frame,
            text="Original files are never modified. Converted files are saved separately.",
            font=("Helvetica", 9),
            foreground="gray"
        )
        notice_label.grid(row=1, column=0, pady=(0, 10), sticky=tk.W)

        # Input selection section
        input_frame = ttk.LabelFrame(main_frame, text="Input Files", padding="10")
        input_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        input_frame.columnconfigure(0, weight=1)

        ttk.Button(
            input_frame,
            text="Select Files",
            command=self._select_files
        ).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))

        ttk.Button(
            input_frame,
            text="Select Folder",
            command=self._select_folder
        ).grid(row=0, column=1, sticky=tk.W, padx=5)

        self.input_label = ttk.Label(input_frame, text="No files selected")
        self.input_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))

        # Output directory section
        output_frame = ttk.LabelFrame(main_frame, text="Output Directory", padding="10")
        output_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)
        output_frame.columnconfigure(0, weight=1)

        ttk.Button(
            output_frame,
            text="Browse",
            command=self._select_output_dir
        ).grid(row=0, column=0, sticky=tk.W)

        self.output_label = ttk.Label(output_frame, text="No output directory selected")
        self.output_label.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))

        # Conversion settings section
        settings_frame = ttk.LabelFrame(main_frame, text="Conversion Settings", padding="10")
        settings_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)

        self.resample_16k_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            settings_frame,
            text="Resample to 16 kHz",
            variable=self.resample_16k_var
        ).grid(row=0, column=0, sticky=tk.W)

        self.mono_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            settings_frame,
            text="Convert to mono",
            variable=self.mono_var
        ).grid(row=0, column=1, sticky=tk.W, padx=20)

        # Convert button
        self.convert_button = ttk.Button(
            main_frame,
            text="Convert",
            command=self._start_conversion
        )
        self.convert_button.grid(row=5, column=0, pady=10)

        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.grid(row=6, column=0, sticky=(tk.W, tk.E), pady=5)
        progress_frame.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(
            progress_frame,
            orient=tk.HORIZONTAL,
            mode='determinate'
        )
        self.progress.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        self.status_label = ttk.Label(progress_frame, text="Ready")
        self.status_label.grid(row=1, column=0, sticky=tk.W)

        # Results section
        results_frame = ttk.LabelFrame(main_frame, text="Conversion Results", padding="10")
        results_frame.grid(row=7, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)

        self.results_text = scrolledtext.ScrolledText(
            results_frame,
            height=15,
            width=80,
            state='disabled'
        )
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Open output folder button
        self.open_folder_button = ttk.Button(
            main_frame,
            text="Open Output Folder",
            command=self._open_output_folder,
            state='disabled'
        )
        self.open_folder_button.grid(row=8, column=0, pady=5)

        # Clear button
        ttk.Button(
            main_frame,
            text="Clear",
            command=self._clear
        ).grid(row=9, column=0, pady=5)

    def _select_files(self):
        """Select individual audio files."""
        files = filedialog.askopenfilenames(
            title="Select Audio/Video Files",
            filetypes=[
                ("All Supported", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wma *.aiff *.au *.ac3 *.dts *.mp2 *.mpg *.mpeg *.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.mts *.m2ts *.ts *.3gp *.asf *.rm *.vob *.mxf *.m4v"),
                ("Audio Files", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus *.wma *.aiff *.au *.ac3 *.dts *.mp2"),
                ("Video Files", "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.mts *.m2ts *.ts *.mpg *.mpeg *.3gp *.asf *.rm *.vob *.mxf *.m4v"),
                ("All Files", "*.*")
            ]
        )

        if files:
            self.input_files = list(files)
            self.input_folder = None
            self.input_label.config(text=f"{len(files)} file(s) selected")

    def _select_folder(self):
        """Select a folder containing audio files."""
        folder = filedialog.askdirectory(title="Select Folder with Audio Files")

        if folder:
            self.input_folder = Path(folder)
            self.input_files = []

            # Find all supported audio/video files
            for ext in self.inspector.SUPPORTED_AUDIO_EXTS | self.inspector.SUPPORTED_VIDEO_EXTS:
                self.input_files.extend(self.input_folder.glob(f"*{ext}"))
                self.input_files.extend(self.input_folder.glob(f"*{ext.upper()}"))

            self.input_files = [str(f) for f in self.input_files]
            self.input_label.config(text=f"{len(self.input_files)} file(s) in folder")

    def _select_output_dir(self):
        """Select output directory."""
        directory = filedialog.askdirectory(title="Select Output Directory")

        if directory:
            self.output_dir = Path(directory)
            self.output_label.config(text=str(self.output_dir))
            self.open_folder_button.config(state='normal')

    def _start_conversion(self):
        """Start the conversion process in a separate thread."""
        if not self.input_files:
            messagebox.showwarning("Warning", "Please select input files first")
            return

        if not self.output_dir:
            messagebox.showwarning("Warning", "Please select output directory first")
            return

        if self.converting:
            return

        self.converting = True
        self.convert_button.config(state='disabled')
        self.results_text.config(state='normal')
        self.results_text.delete(1.0, tk.END)
        self.results_text.config(state='disabled')

        # Start conversion in background thread
        thread = threading.Thread(target=self._run_conversion)
        thread.daemon = True
        thread.start()

    def _run_conversion(self):
        """Run the conversion process."""
        try:
            sample_rate = 16000 if self.resample_16k_var.get() else None
            mono = self.mono_var.get()

            def progress_callback(current, total, file_path, result):
                # Update GUI in main thread
                self.root.after(0, self._update_progress, current, total, file_path, result)

            # Run batch conversion
            batch_result = self.converter.batch_convert(
                self.input_files,
                self.output_dir,
                sample_rate=sample_rate,
                mono=mono,
                progress_callback=progress_callback
            )

            # Final update
            self.root.after(0, self._conversion_complete, batch_result)

        except Exception as e:
            # Handle any unexpected errors
            self.root.after(0, self._conversion_error, str(e))

    def _update_progress(self, current, total, file_path, result):
        """Update progress display."""
        progress = (current / total) * 100
        self.progress['value'] = progress
        self.status_label.config(text=f"Processing {current}/{total}: {Path(file_path).name}")

        # Add result to display
        self.results_text.config(state='normal')

        if result['success']:
            msg = f"✓ {Path(file_path).name}"
            if result.get('warning'):
                msg += f" (Warning: {result['warning']})"
            self.results_text.insert(tk.END, msg + "\n", 'success')
        else:
            self.results_text.insert(tk.END, f"✗ {Path(file_path).name}: {result.get('error', 'Unknown error')}\n", 'error')

        self.results_text.see(tk.END)
        self.results_text.config(state='disabled')

    def _conversion_complete(self, batch_result):
        """Handle conversion completion."""
        self.converting = False
        self.convert_button.config(state='normal')
        self.status_label.config(
            text=f"Complete: {batch_result['successful']} successful, {batch_result['failed']} failed"
        )

        # Add summary
        self.results_text.config(state='normal')
        self.results_text.insert(tk.END, "\n" + "="*60 + "\n")
        self.results_text.insert(tk.END, f"Total: {batch_result['total']}\n")
        self.results_text.insert(tk.END, f"Successful: {batch_result['successful']}\n")
        self.results_text.insert(tk.END, f"Failed: {batch_result['failed']}\n")
        self.results_text.see(tk.END)
        self.results_text.config(state='disabled')

        # Show message box if there were failures
        if batch_result['failed'] > 0:
            messagebox.showwarning(
                "Conversion Complete",
                f"Conversion finished with {batch_result['failed']} failure(s). Check the results for details."
            )
        else:
            messagebox.showinfo(
                "Conversion Complete",
                f"Successfully converted {batch_result['successful']} file(s)."
            )

    def _conversion_error(self, error_message):
        """Handle unexpected conversion errors."""
        self.converting = False
        self.convert_button.config(state='normal')
        self.status_label.config(text="Error occurred")

        # Display error in results
        self.results_text.config(state='normal')
        self.results_text.insert(tk.END, f"\n❌ UNEXPECTED ERROR:\n{error_message}\n", 'error')
        self.results_text.see(tk.END)
        self.results_text.config(state='disabled')

        # Show error dialog
        messagebox.showerror(
            "Conversion Error",
            f"An unexpected error occurred:\n\n{error_message}\n\nPlease check the file format and try again."
        )

    def _open_output_folder(self):
        """Open the output folder in the system file manager."""
        if not self.output_dir:
            return

        try:
            if platform.system() == "Windows":
                subprocess.run(["explorer", str(self.output_dir)])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", str(self.output_dir)])
            else:  # Linux
                subprocess.run(["xdg-open", str(self.output_dir)])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {e}")

    def _clear(self):
        """Clear all selections and results."""
        self.input_files = []
        self.input_folder = None
        self.output_dir = None
        self.input_label.config(text="No files selected")
        self.output_label.config(text="No output directory selected")
        self.open_folder_button.config(state='disabled')
        self.progress['value'] = 0
        self.status_label.config(text="Ready")
        self.results_text.config(state='normal')
        self.results_text.delete(1.0, tk.END)
        self.results_text.config(state='disabled')


def main():
    """Main entry point."""
    root = tk.Tk()
    app = AudioConverterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
