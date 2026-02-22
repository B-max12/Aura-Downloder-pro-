import os
import sys
import subprocess
import threading
import re
import urllib.parse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Auto-install dependencies if missing to ensure smooth experience for the user
def install_and_import(package, import_name=None):
    if import_name is None:
        import_name = package
    try:
        __import__(import_name)
    except ImportError:
        print(f"Installing missing required package: {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_and_import("customtkinter")
install_and_import("yt-dlp", "yt_dlp")
install_and_import("requests")
install_and_import("Pillow", "PIL")

import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk
from yt_dlp import YoutubeDL
import requests
from PIL import Image

# Set modern aesthetic
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ==============================================================================
#  SOLID COLOR PALETTE
# ==============================================================================
CLR_BG_DARK      = "#0b0e14"   # Main window background
CLR_PANEL         = "#141922"   # Panels / frames
CLR_PANEL_INNER   = "#1a2030"   # Inner panels / cards
CLR_HEADER        = "#101520"   # Header bar
CLR_ACCENT        = "#00aaff"   # Primary accent (titles, highlights)
CLR_TEXT          = "#e0e0e0"   # Main text
CLR_TEXT_DIM      = "#808a9a"   # Dimmed / hint text
CLR_BORDER        = "#2a3040"   # Borders
CLR_BTN_PRIMARY   = "#0078d4"   # Primary action button
CLR_BTN_PRIMARY_H = "#005fa3"   # Primary hover
CLR_BTN_SUCCESS   = "#1a8a3f"   # Green button (MP3, success)
CLR_BTN_SUCCESS_H = "#14703a"   # Green hover
CLR_BTN_DANGER    = "#c0392b"   # Red button (delete, cancel)
CLR_BTN_DANGER_H  = "#a93327"   # Red hover
CLR_BTN_WARN      = "#d4780a"   # Orange button (accelerated)
CLR_BTN_WARN_H    = "#b5660a"   # Orange hover
CLR_BTN_NEUTRAL   = "#3a4050"   # Neutral button (browse, pause)
CLR_BTN_NEUTRAL_H = "#4a5060"   # Neutral hover
CLR_BTN_BEST      = "#b84a10"   # Best quality button
CLR_BTN_BEST_H    = "#d0601e"   # Best quality hover
CLR_BTN_QUALITY   = "#2a5a8f"   # Quality button
CLR_BTN_QUALITY_H = "#1e4570"   # Quality hover
CLR_NOTEPAD       = "#111825"   # Right notepad bg
CLR_NOTEPAD_LIST  = "#0e1420"   # Notepad scrollable list bg
CLR_LINK_CARD     = "#161e2c"   # Link card in notepad
CLR_QUEUE_BG      = "#0e1420"   # Queue item background
CLR_PROGRESS_FG   = "#00aaff"   # Progress bar fill
CLR_PROGRESS_BG   = "#1a2030"   # Progress bar background

# ==============================================================================
#  CONSTANTS
# ==============================================================================
CHUNK_COUNT = 8           # Number of parallel chunks for accelerated downloads
MAX_CONCURRENT_DL = 3     # Max concurrent downloads in the queue
CLIPBOARD_POLL_MS = 1000  # Clipboard check interval in milliseconds

# Known direct-download file extensions
DIRECT_FILE_EXTENSIONS = {
    '.exe', '.msi', '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
    '.iso', '.img', '.dmg',
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
    '.mp3', '.flac', '.wav', '.aac', '.ogg',
    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
    '.apk', '.deb', '.rpm', '.appimage',
    '.bin', '.dat', '.torrent',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff',
}

# ==============================================================================
#  HELPER FUNCTIONS
# ==============================================================================

def show_notification(title, message):
    """Shows a Windows 10/11 toast notification using native PowerShell."""
    if os.name != 'nt':
        return
    safe_title = title.replace("'", "''")
    safe_message = message.replace("'", "''")
    ps_script = f"""
[reflection.assembly]::loadwithpartialname("System.Windows.Forms") | Out-Null
[reflection.assembly]::loadwithpartialname("System.Drawing") | Out-Null
$notify = New-Object system.windows.forms.notifyicon
$notify.icon = [System.Drawing.SystemIcons]::Information
$notify.balloontipicon = "Info"
$notify.balloontiptitle = '{safe_title}'
$notify.balloontiptext = '{safe_message}'
$notify.visible = $True
$notify.showballoontip(5000)
Start-Sleep -Seconds 5
$notify.dispose()
"""
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception:
        pass


def get_default_download_location():
    if os.name == 'nt':
        user_profile = os.environ.get('USERPROFILE')
        if user_profile:
            return os.path.join(user_profile, 'Downloads')
    return os.path.join(os.path.expanduser('~'), 'Downloads')


def clean_url(url):
    """
    Remove playlist parameters from YouTube URLs so it focuses on the single video.
    Strips: list, index, start_radio, etc.
    """
    url = url.strip()
    parsed = urllib.parse.urlparse(url)

    # Only strip for YouTube domains
    yt_domains = ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be')
    if parsed.hostname and parsed.hostname.lower() in yt_domains:
        params = urllib.parse.parse_qs(parsed.query)
        # Remove playlist-related params
        for key in ['list', 'index', 'start_radio', 'rdm', 'playnext']:
            params.pop(key, None)
        clean_query = urllib.parse.urlencode(params, doseq=True)
        parsed = parsed._replace(query=clean_query)
        url = urllib.parse.urlunparse(parsed)
    return url


def is_direct_file_url(url):
    """Check if a URL points to a direct downloadable file."""
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in DIRECT_FILE_EXTENSIONS)
    except Exception:
        return False


def get_filename_from_url(url):
    """Extract a filename from a URL."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    name = os.path.basename(path)
    if not name:
        name = "downloaded_file"
    return urllib.parse.unquote(name)


def is_url(text):
    """Check if text looks like a URL."""
    text = text.strip()
    return bool(re.match(r'^https?://', text, re.IGNORECASE))


# ==============================================================================
#  CHUNKED DOWNLOADER ENGINE — with Pause / Resume / Cancel
# ==============================================================================

class ChunkedDownloader:
    """
    Downloads a file from a direct URL using multiple concurrent connections.
    Splits the file into CHUNK_COUNT parts, downloads them in parallel,
    and stitches them back together for maximum speed.
    Supports pause, resume, and cancel.
    """

    def __init__(self, url, save_path, num_chunks=CHUNK_COUNT,
                 progress_callback=None, status_callback=None):
        self.url = url
        self.save_path = save_path
        self.num_chunks = num_chunks
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self.total_size = 0
        self.downloaded_bytes = [0] * num_chunks
        self.cancelled = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start in un-paused state
        self._lock = threading.Lock()

    def pause(self):
        """Pause the download."""
        self._pause_event.clear()
        self._report_status("⏸️ Paused")

    def resume(self):
        """Resume the download."""
        self._pause_event.set()
        self._report_status("⏳ Resuming...")

    def cancel(self):
        """Cancel the download."""
        self.cancelled = True
        self._pause_event.set()  # Unblock any paused threads

    @property
    def is_paused(self):
        return not self._pause_event.is_set()

    def _report_status(self, text):
        if self.status_callback:
            self.status_callback(text)

    def _report_progress(self):
        if self.progress_callback:
            total_dl = sum(self.downloaded_bytes)
            self.progress_callback(total_dl, self.total_size)

    def _download_chunk(self, chunk_index, start, end, temp_path):
        """Download a single chunk of the file."""
        headers = {'Range': f'bytes={start}-{end}'}
        try:
            resp = requests.get(self.url, headers=headers, stream=True, timeout=60)
            resp.raise_for_status()
            with open(temp_path, 'wb') as f:
                for data in resp.iter_content(chunk_size=65536):
                    # Check pause
                    self._pause_event.wait()
                    if self.cancelled:
                        return False
                    f.write(data)
                    with self._lock:
                        self.downloaded_bytes[chunk_index] += len(data)
                    self._report_progress()
            return True
        except Exception as e:
            if not self.cancelled:
                self._report_status(f"Chunk {chunk_index + 1} error: {e}")
            return False

    def download(self):
        """Execute the chunked download. Returns True on success."""
        self._report_status("Analyzing file...")

        try:
            head = requests.head(self.url, allow_redirects=True, timeout=30)
            self.total_size = int(head.headers.get('content-length', 0))
            accept_ranges = head.headers.get('accept-ranges', 'none').lower()
        except Exception as e:
            self._report_status(f"Error: {e}")
            return False

        if accept_ranges != 'bytes' or self.total_size < 1024 * 1024:
            return self._single_stream_download()

        self._report_status(f"Splitting into {self.num_chunks} chunks ({self.total_size / (1024*1024):.1f} MB)...")

        chunk_size = self.total_size // self.num_chunks
        temp_dir = os.path.dirname(self.save_path)
        temp_files = []
        futures = []

        with ThreadPoolExecutor(max_workers=self.num_chunks) as executor:
            for i in range(self.num_chunks):
                start = i * chunk_size
                end = (start + chunk_size - 1) if i < self.num_chunks - 1 else self.total_size - 1
                temp_path = os.path.join(temp_dir, f".aura_chunk_{i}_{os.path.basename(self.save_path)}")
                temp_files.append(temp_path)
                futures.append(executor.submit(self._download_chunk, i, start, end, temp_path))

            results = [f.result() for f in futures]

        if self.cancelled or not all(results):
            for tf in temp_files:
                try:
                    os.remove(tf)
                except OSError:
                    pass
            return False

        # Stitch chunks together
        self._report_status("🔗 Stitching file parts together...")
        try:
            with open(self.save_path, 'wb') as out_file:
                for tf in temp_files:
                    with open(tf, 'rb') as chunk_file:
                        while True:
                            data = chunk_file.read(1024 * 1024)
                            if not data:
                                break
                            out_file.write(data)
                    os.remove(tf)
        except Exception as e:
            self._report_status(f"Stitch error: {e}")
            return False

        self._report_status("✅ Download complete!")
        return True

    def _single_stream_download(self):
        """Fallback: single-stream download."""
        self._report_status("Downloading (single stream)...")
        try:
            resp = requests.get(self.url, stream=True, timeout=120)
            resp.raise_for_status()
            self.total_size = int(resp.headers.get('content-length', 0))

            with open(self.save_path, 'wb') as f:
                for data in resp.iter_content(chunk_size=65536):
                    self._pause_event.wait()
                    if self.cancelled:
                        return False
                    f.write(data)
                    with self._lock:
                        self.downloaded_bytes[0] += len(data)
                    self._report_progress()
            return True
        except Exception as e:
            if not self.cancelled:
                self._report_status(f"Download error: {e}")
            return False


# ==============================================================================
#  DOWNLOAD QUEUE ITEM WIDGET — with Pause / Resume / Cancel buttons
# ==============================================================================

class DownloadQueueItem(ctk.CTkFrame):
    """A single item in the download queue showing title, progress, status, and controls."""

    def __init__(self, master, title, url, **kwargs):
        super().__init__(master, fg_color=CLR_QUEUE_BG, corner_radius=8, **kwargs)
        self.grid_columnconfigure(0, weight=1)

        self.title_text = title
        self.url = url
        self._downloader = None          # Reference to ChunkedDownloader (direct downloads)
        self._ytdlp_paused = False       # For yt-dlp pause emulation
        self._ytdlp_cancelled = False    # For yt-dlp cancel
        self._pause_event = threading.Event()
        self._pause_event.set()

        # Row 0: Title + control buttons
        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.grid(row=0, column=0, padx=8, pady=(6, 0), sticky="ew")
        top_row.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            top_row, text=f"  {title[:50]}", font=("Segoe UI", 12, "bold"),
            anchor="w", text_color=CLR_TEXT
        )
        self.title_label.grid(row=0, column=0, sticky="ew")

        # Control buttons
        btn_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=(5, 0))

        self.pause_btn = ctk.CTkButton(
            btn_frame, text="⏸", width=30, height=26,
            font=("Segoe UI", 13), corner_radius=6,
            fg_color=CLR_BTN_NEUTRAL, hover_color=CLR_BTN_NEUTRAL_H,
            command=self._on_pause
        )
        self.pause_btn.grid(row=0, column=0, padx=2)

        self.resume_btn = ctk.CTkButton(
            btn_frame, text="▶", width=30, height=26,
            font=("Segoe UI", 13), corner_radius=6,
            fg_color=CLR_BTN_SUCCESS, hover_color=CLR_BTN_SUCCESS_H,
            command=self._on_resume
        )
        self.resume_btn.grid(row=0, column=1, padx=2)
        self.resume_btn.configure(state="disabled")

        self.cancel_btn = ctk.CTkButton(
            btn_frame, text="✕", width=30, height=26,
            font=("Segoe UI", 13, "bold"), corner_radius=6,
            fg_color=CLR_BTN_DANGER, hover_color=CLR_BTN_DANGER_H,
            command=self._on_cancel
        )
        self.cancel_btn.grid(row=0, column=2, padx=2)

        # Row 1: Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self, height=8, corner_radius=4,
            progress_color=CLR_PROGRESS_FG, fg_color=CLR_PROGRESS_BG
        )
        self.progress_bar.grid(row=1, column=0, padx=10, pady=(4, 0), sticky="ew")
        self.progress_bar.set(0)

        # Row 2: Status text
        self.status_label = ctk.CTkLabel(
            self, text="Queued...", font=("Segoe UI", 10),
            text_color=CLR_TEXT_DIM, anchor="w"
        )
        self.status_label.grid(row=2, column=0, padx=10, pady=(0, 6), sticky="ew")

    def set_downloader(self, downloader):
        """Attach a ChunkedDownloader instance for pause/resume/cancel."""
        self._downloader = downloader

    def _on_pause(self):
        self.pause_btn.configure(state="disabled")
        self.resume_btn.configure(state="normal")
        if self._downloader:
            self._downloader.pause()
        else:
            # yt-dlp pause emulation
            self._ytdlp_paused = True
            self._pause_event.clear()
            self.update_status("⏸️ Paused")

    def _on_resume(self):
        self.resume_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        if self._downloader:
            self._downloader.resume()
        else:
            self._ytdlp_paused = False
            self._pause_event.set()
            self.update_status("⏳ Resuming...")

    def _on_cancel(self):
        self.pause_btn.configure(state="disabled")
        self.resume_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        if self._downloader:
            self._downloader.cancel()
        else:
            self._ytdlp_cancelled = True
            self._pause_event.set()  # Unblock if paused
        self.update_status("❌ Cancelled")

    def update_progress(self, value):
        try:
            self.progress_bar.set(value)
        except Exception:
            pass

    def update_status(self, text):
        try:
            self.status_label.configure(text=text)
        except Exception:
            pass

    def mark_complete(self):
        """Disable all controls and show completed state."""
        self.pause_btn.configure(state="disabled")
        self.resume_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        self.update_status("✅ Complete!")
        self.update_progress(1.0)

    def mark_failed(self, msg=""):
        """Disable all controls and show failed state."""
        self.pause_btn.configure(state="disabled")
        self.resume_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        self.update_status(f"❌ Failed{': ' + msg[:40] if msg else ''}")


# ==============================================================================
#  MAIN APPLICATION
# ==============================================================================

class AuraDownloaderPro(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Aura Downloader Pro")
        self.geometry("1100x750")
        self.minsize(900, 600)
        self.configure(fg_color=CLR_BG_DARK)

        # Try to set the window icon from logo
        self._set_app_icon()

        # State
        self.download_dir = get_default_download_location()
        self.video_info = None
        self.sorted_formats = []
        self.clipboard_links = []
        self.last_clipboard = ""
        self.download_queue_widgets = []
        self.download_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DL)

        # Build UI
        self._create_layout()
        self._start_clipboard_monitor()

    def _set_app_icon(self):
        """Set the window icon from the logo PNG."""
        try:
            logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aura-downloder-pro.png")
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                icon_img = img.resize((64, 64), Image.LANCZOS)
                ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".aura_icon.ico")
                icon_img.save(ico_path, format='ICO', sizes=[(64, 64)])
                self.iconbitmap(ico_path)
        except Exception:
            pass

    # ==========================================================================
    #  LAYOUT
    # ==========================================================================
    def _create_layout(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._create_header()

        # Left panel
        self.left_frame = ctk.CTkFrame(self, fg_color=CLR_BG_DARK)
        self.left_frame.grid(row=1, column=0, padx=(15, 5), pady=(0, 15), sticky="nsew")
        self.left_frame.grid_columnconfigure(0, weight=1)
        self.left_frame.grid_rowconfigure(2, weight=1)

        self._create_url_section()
        self._create_path_section()
        self._create_qualities_section()
        self._create_download_queue_section()
        self._create_status_section()

        # Right panel
        self._create_notepad_panel()

    def _create_header(self):
        self.header_frame = ctk.CTkFrame(
            self, height=80, corner_radius=0, fg_color=CLR_HEADER
        )
        self.header_frame.grid(row=0, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        self.header_frame.grid_columnconfigure(1, weight=1)
        self.header_frame.grid_propagate(False)

        # Logo
        try:
            logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aura-downloder-pro.png")
            if os.path.exists(logo_path):
                logo_img = ctk.CTkImage(
                    light_image=Image.open(logo_path),
                    dark_image=Image.open(logo_path),
                    size=(55, 55)
                )
                logo_label = ctk.CTkLabel(self.header_frame, image=logo_img, text="")
                logo_label.grid(row=0, column=0, padx=(20, 10), pady=12)
        except Exception:
            pass

        title_label = ctk.CTkLabel(
            self.header_frame, text="Aura Downloader Pro",
            font=("Segoe UI", 24, "bold"), text_color=CLR_ACCENT
        )
        title_label.grid(row=0, column=1, padx=5, pady=12, sticky="w")

        sub_label = ctk.CTkLabel(
            self.header_frame,
            text="YouTube  •  Software  •  Movies  •  Any File",
            font=("Segoe UI", 11), text_color=CLR_TEXT_DIM
        )
        sub_label.grid(row=0, column=2, padx=(0, 20), pady=12, sticky="e")

    def _create_url_section(self):
        self.url_frame = ctk.CTkFrame(self.left_frame, fg_color=CLR_PANEL, corner_radius=10)
        self.url_frame.grid(row=0, column=0, padx=5, pady=(10, 5), sticky="ew")
        self.url_frame.grid_columnconfigure(1, weight=1)

        url_label = ctk.CTkLabel(
            self.url_frame, text="  Enter URL:",
            font=("Segoe UI", 13, "bold"), text_color=CLR_TEXT
        )
        url_label.grid(row=0, column=0, padx=10, pady=10)

        self.url_entry = ctk.CTkEntry(
            self.url_frame,
            placeholder_text="Paste any URL — YouTube, file, software, etc.",
            height=38, font=("Segoe UI", 12),
            fg_color=CLR_PANEL_INNER, border_color=CLR_BORDER
        )
        self.url_entry.grid(row=0, column=1, padx=5, pady=10, sticky="ew")

        self.fetch_btn = ctk.CTkButton(
            self.url_frame, text="Fetch", command=self.start_fetch,
            font=("Segoe UI", 13, "bold"), width=100, height=38,
            fg_color=CLR_BTN_PRIMARY, hover_color=CLR_BTN_PRIMARY_H, corner_radius=8
        )
        self.fetch_btn.grid(row=0, column=2, padx=10, pady=10)

    def _create_path_section(self):
        self.path_frame = ctk.CTkFrame(self.left_frame, fg_color=CLR_PANEL, corner_radius=10)
        self.path_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.path_frame.grid_columnconfigure(1, weight=1)

        path_label = ctk.CTkLabel(
            self.path_frame, text="  Save To:",
            font=("Segoe UI", 12, "bold"), text_color=CLR_TEXT
        )
        path_label.grid(row=0, column=0, padx=10, pady=8)

        self.path_entry = ctk.CTkEntry(
            self.path_frame, font=("Segoe UI", 11),
            fg_color=CLR_PANEL_INNER, border_color=CLR_BORDER
        )
        self.path_entry.insert(0, self.download_dir)
        self.path_entry.configure(state="readonly")
        self.path_entry.grid(row=0, column=1, padx=5, pady=8, sticky="ew")

        self.browse_btn = ctk.CTkButton(
            self.path_frame, text="Browse", width=80,
            command=self.browse_location, height=32,
            fg_color=CLR_BTN_NEUTRAL, hover_color=CLR_BTN_NEUTRAL_H, corner_radius=8
        )
        self.browse_btn.grid(row=0, column=2, padx=10, pady=8)

    def _create_qualities_section(self):
        self.qualities_frame = ctk.CTkScrollableFrame(
            self.left_frame, label_text="  Available Options (Click to Download)",
            label_font=("Segoe UI", 13, "bold"),
            fg_color=CLR_PANEL, corner_radius=10,
            scrollbar_button_color=CLR_BTN_NEUTRAL
        )
        self.qualities_frame.grid(row=2, column=0, padx=5, pady=5, sticky="nsew")
        self.qualities_frame.grid_columnconfigure(0, weight=1)
        self.quality_buttons = []

    def _create_download_queue_section(self):
        self.queue_frame = ctk.CTkScrollableFrame(
            self.left_frame, label_text="  Download Queue",
            label_font=("Segoe UI", 12, "bold"), height=140,
            fg_color=CLR_PANEL, corner_radius=10,
            scrollbar_button_color=CLR_BTN_NEUTRAL
        )
        self.queue_frame.grid(row=3, column=0, padx=5, pady=5, sticky="ew")
        self.queue_frame.grid_columnconfigure(0, weight=1)

    def _create_status_section(self):
        self.status_frame = ctk.CTkFrame(self.left_frame, fg_color=CLR_PANEL, corner_radius=10)
        self.status_frame.grid(row=4, column=0, padx=5, pady=(5, 5), sticky="ew")
        self.status_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            self.status_frame, text="Status: Ready — paste any URL to begin",
            font=("Segoe UI", 11), anchor="w", text_color=CLR_TEXT
        )
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(
            self.status_frame, height=8, corner_radius=4,
            progress_color=CLR_PROGRESS_FG, fg_color=CLR_PROGRESS_BG
        )
        self.progress_bar.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        self.progress_bar.set(0)

    # ==========================================================================
    #  CLIPBOARD NOTEPAD PANEL
    # ==========================================================================
    def _create_notepad_panel(self):
        self.notepad_frame = ctk.CTkFrame(
            self, fg_color=CLR_NOTEPAD,
            border_width=1, border_color=CLR_BORDER, corner_radius=10
        )
        self.notepad_frame.grid(row=1, column=1, padx=(5, 15), pady=(0, 15), sticky="nsew")
        self.notepad_frame.grid_columnconfigure(0, weight=1)
        self.notepad_frame.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self.notepad_frame, fg_color="transparent")
        header.grid(row=0, column=0, padx=8, pady=(10, 5), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        notepad_title = ctk.CTkLabel(
            header, text="  Link Catcher",
            font=("Segoe UI", 14, "bold"), text_color=CLR_ACCENT
        )
        notepad_title.grid(row=0, column=0, sticky="w")

        clear_btn = ctk.CTkButton(
            header, text="Clear", width=55, height=26,
            font=("Segoe UI", 10, "bold"), corner_radius=6,
            fg_color=CLR_BTN_DANGER, hover_color=CLR_BTN_DANGER_H,
            command=self._clear_all_links
        )
        clear_btn.grid(row=0, column=1, padx=(5, 0))

        download_all_btn = ctk.CTkButton(
            header, text="DL All", width=55, height=26,
            font=("Segoe UI", 10, "bold"), corner_radius=6,
            fg_color=CLR_BTN_SUCCESS, hover_color=CLR_BTN_SUCCESS_H,
            command=self._download_all_links
        )
        download_all_btn.grid(row=0, column=2, padx=(5, 0))

        # Scrollable link list
        self.links_scroll = ctk.CTkScrollableFrame(
            self.notepad_frame, fg_color=CLR_NOTEPAD_LIST, corner_radius=8,
            scrollbar_button_color=CLR_BTN_NEUTRAL
        )
        self.links_scroll.grid(row=1, column=0, padx=8, pady=5, sticky="nsew")
        self.links_scroll.grid_columnconfigure(0, weight=1)

        # Hint
        hint_label = ctk.CTkLabel(
            self.notepad_frame,
            text="Copy any URL → auto-captured here",
            font=("Segoe UI", 9), text_color=CLR_TEXT_DIM
        )
        hint_label.grid(row=2, column=0, padx=8, pady=(0, 8))

        self.link_widgets = []

    def _add_link_to_notepad(self, url):
        """Add a detected URL to the clipboard notepad."""
        if url in self.clipboard_links:
            return
        self.clipboard_links.append(url)

        row_idx = len(self.link_widgets)
        link_frame = ctk.CTkFrame(
            self.links_scroll, fg_color=CLR_LINK_CARD, corner_radius=8
        )
        link_frame.grid(row=row_idx, column=0, padx=4, pady=3, sticky="ew")
        link_frame.grid_columnconfigure(0, weight=1)

        display_url = url if len(url) <= 35 else url[:32] + "..."
        url_label = ctk.CTkLabel(
            link_frame, text=display_url, font=("Segoe UI", 10),
            anchor="w", text_color=CLR_TEXT
        )
        url_label.grid(row=0, column=0, padx=8, pady=6, sticky="w")

        btn_frame = ctk.CTkFrame(link_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=(0, 5), pady=4)

        paste_btn = ctk.CTkButton(
            btn_frame, text="📋", width=30, height=26,
            font=("Segoe UI", 11), corner_radius=6,
            fg_color=CLR_BTN_PRIMARY, hover_color=CLR_BTN_PRIMARY_H,
            command=lambda u=url: self._paste_link(u)
        )
        paste_btn.grid(row=0, column=0, padx=2)

        delete_btn = ctk.CTkButton(
            btn_frame, text="✕", width=30, height=26,
            font=("Segoe UI", 11, "bold"), corner_radius=6,
            fg_color=CLR_BTN_NEUTRAL, hover_color=CLR_BTN_DANGER,
            command=lambda u=url, f=link_frame: self._delete_link(u, f)
        )
        delete_btn.grid(row=0, column=1, padx=2)

        self.link_widgets.append((link_frame, url))

    def _paste_link(self, url):
        """Paste a link from notepad into the URL bar and auto-fetch."""
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url)
        self.start_fetch()

    def _delete_link(self, url, frame):
        """Delete a single link from the notepad."""
        if url in self.clipboard_links:
            self.clipboard_links.remove(url)
        frame.destroy()
        self.link_widgets = [(f, u) for f, u in self.link_widgets if u != url]

    def _clear_all_links(self):
        for frame, _ in self.link_widgets:
            frame.destroy()
        self.link_widgets.clear()
        self.clipboard_links.clear()

    def _download_all_links(self):
        if not self.clipboard_links:
            messagebox.showinfo("No Links", "No links in the notepad to download.")
            return
        for url in list(self.clipboard_links):
            self._queue_smart_download(url)

    # ==========================================================================
    #  CLIPBOARD MONITOR
    # ==========================================================================
    def _start_clipboard_monitor(self):
        try:
            current = self.clipboard_get()
        except (tk.TclError, Exception):
            current = ""

        if current != self.last_clipboard and is_url(current):
            self.last_clipboard = current
            self._add_link_to_notepad(current.strip())

        self.after(CLIPBOARD_POLL_MS, self._start_clipboard_monitor)

    # ==========================================================================
    #  BROWSE / STATUS
    # ==========================================================================
    def browse_location(self):
        new_dir = filedialog.askdirectory(initialdir=self.download_dir)
        if new_dir:
            self.download_dir = os.path.normpath(new_dir)
            self.path_entry.configure(state="normal")
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, self.download_dir)
            self.path_entry.configure(state="readonly")

    def update_status(self, text, progress=None):
        self.status_label.configure(text=f"Status: {text}")
        if progress is not None:
            self.progress_bar.set(progress)
        self.update_idletasks()

    # ==========================================================================
    #  SMART FETCH — DETECT URL TYPE & STRIP PLAYLIST
    # ==========================================================================
    def start_fetch(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please enter a valid URL.")
            return

        if not is_url(url):
            messagebox.showwarning("Input Error", "Please enter a valid URL starting with http:// or https://")
            return

        # *** CLEAN URL — remove playlist params ***
        url = clean_url(url)
        # Update the entry with the cleaned URL
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url)

        self.fetch_btn.configure(state="disabled")
        self.update_status("Analyzing URL...", 0)

        for btn in self.quality_buttons:
            btn.destroy()
        self.quality_buttons.clear()

        if is_direct_file_url(url):
            self.after(0, self._display_direct_download, url)
        else:
            threading.Thread(target=self.fetch_info, args=(url,), daemon=True).start()

    def _display_direct_download(self, url):
        """Show download options for a direct file URL."""
        filename = get_filename_from_url(url)
        self.update_status(f"Direct file detected: {filename}", 0)
        self.fetch_btn.configure(state="normal")

        info_label = ctk.CTkLabel(
            self.qualities_frame,
            text=f"  Direct File: {filename}",
            font=("Segoe UI", 14, "bold"), text_color=CLR_ACCENT, anchor="w"
        )
        info_label.grid(row=0, column=0, padx=15, pady=(5, 10), sticky="w")
        self.quality_buttons.append(info_label)

        dl_btn = ctk.CTkButton(
            self.qualities_frame,
            text=f"  Accelerated Download (x{CHUNK_COUNT} chunks)",
            command=lambda: self._queue_direct_download(url, filename),
            height=45, font=("Segoe UI", 14, "bold"), corner_radius=8,
            fg_color=CLR_BTN_WARN, hover_color=CLR_BTN_WARN_H
        )
        dl_btn.grid(row=1, column=0, pady=5, padx=15, sticky="ew")
        self.quality_buttons.append(dl_btn)

        normal_btn = ctk.CTkButton(
            self.qualities_frame,
            text="  Standard Download (single connection)",
            command=lambda: self._queue_direct_download(url, filename, chunked=False),
            height=40, font=("Segoe UI", 13), corner_radius=8,
            fg_color=CLR_BTN_PRIMARY, hover_color=CLR_BTN_PRIMARY_H
        )
        normal_btn.grid(row=2, column=0, pady=5, padx=15, sticky="ew")
        self.quality_buttons.append(normal_btn)

    # ==========================================================================
    #  YT-DLP FETCH (YouTube + 1000s of sites)
    # ==========================================================================
    def fetch_info(self, url):
        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': "in_playlist",
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'nocheckcertificate': True,
            'no_playlist': True,
            'simulate': True,
        }

        try:
            with YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            error_msg = str(e)
            if "Unsupported URL" in error_msg or "No video" in error_msg:
                self.after(0, self._display_generic_download, url)
            else:
                self.after(0, self.fetch_failed, f"Failed to fetch: {e}")
            return

        self.video_info = info
        title = info.get('title', 'Unknown_Video')
        formats = info.get('formats', [])

        video_formats = []
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('resolution') and f.get('ext') == 'mp4':
                fmt_id = f.get('format_id')
                resolution = f.get('resolution')
                height = f.get('height', 0)
                fps = f.get('fps', '')
                filesize = f.get('filesize') or f.get('filesize_approx')

                size_str = f"{filesize / (1024*1024):.2f} MB" if filesize else "Size Unknown"
                fps_str = f"{fps}fps" if fps else ""

                video_formats.append({
                    'format_id': fmt_id,
                    'resolution': resolution,
                    'height': height,
                    'fps': fps_str,
                    'size_str': size_str,
                    'ext': f.get('ext')
                })

        unique_res = {}
        for f in video_formats:
            h = f['height']
            if h not in unique_res:
                unique_res[h] = f

        self.sorted_formats = sorted(unique_res.values(), key=lambda x: x['height'], reverse=True)
        self.after(0, self.display_qualities, title, url)

    def _display_generic_download(self, url):
        """Fallback for unsupported sites: allow generic HTTP download."""
        filename = get_filename_from_url(url)
        self.update_status(f"Generic URL — will download: {filename}", 0)
        self.fetch_btn.configure(state="normal")

        dl_btn = ctk.CTkButton(
            self.qualities_frame,
            text=f"  Download File: {filename}",
            command=lambda: self._queue_direct_download(url, filename),
            height=45, font=("Segoe UI", 14, "bold"), corner_radius=8,
            fg_color=CLR_BTN_WARN, hover_color=CLR_BTN_WARN_H
        )
        dl_btn.grid(row=0, column=0, pady=5, padx=15, sticky="ew")
        self.quality_buttons.append(dl_btn)

    def fetch_failed(self, msg):
        self.update_status("Fetch Failed. Check URL.", 0)
        self.fetch_btn.configure(state="normal")
        messagebox.showerror("Fetch Error", msg)

    def display_qualities(self, title, url):
        self.update_status(f"Found: {title[:50]}...", 0)
        self.fetch_btn.configure(state="normal")

        # MP3 Button
        mp3_btn = ctk.CTkButton(
            self.qualities_frame,
            text="  Audio Only (MP3)",
            command=lambda t=title: self._queue_ytdlp_download(url, "bestaudio/best", t, is_mp3=True),
            height=40, font=("Segoe UI", 14, "bold"), corner_radius=8,
            fg_color=CLR_BTN_SUCCESS, hover_color=CLR_BTN_SUCCESS_H
        )
        mp3_btn.grid(row=0, column=0, pady=(0, 12), padx=15, sticky="ew")
        self.quality_buttons.append(mp3_btn)

        if not self.sorted_formats:
            btn = ctk.CTkButton(
                self.qualities_frame,
                text="  Download Best Available Video",
                command=lambda: self._queue_ytdlp_download(
                    url, "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best", title
                ),
                height=40, font=("Segoe UI", 13, "bold"), corner_radius=8,
                fg_color=CLR_BTN_PRIMARY, hover_color=CLR_BTN_PRIMARY_H
            )
            btn.grid(row=1, column=0, pady=5, padx=15, sticky="ew")
            self.quality_buttons.append(btn)
        else:
            for i, f in enumerate(self.sorted_formats):
                btn_text = f"  {f['resolution']} @ {f['fps']}   |   {f['size_str']}"
                fmt_string = f"{f['format_id']}+bestaudio[ext=m4a]/bestaudio/best"

                is_best = (i == 0)
                fg_col = CLR_BTN_BEST if is_best else CLR_BTN_QUALITY
                hov_col = CLR_BTN_BEST_H if is_best else CLR_BTN_QUALITY_H

                btn = ctk.CTkButton(
                    self.qualities_frame,
                    text=btn_text,
                    command=lambda fmt=fmt_string, t=title: self._queue_ytdlp_download(url, fmt, t),
                    height=40,
                    font=("Segoe UI", 14, "bold" if is_best else "normal"),
                    corner_radius=8,
                    fg_color=fg_col, hover_color=hov_col
                )
                btn.grid(row=i + 1, column=0, pady=6, padx=15, sticky="ew")
                self.quality_buttons.append(btn)

    # ==========================================================================
    #  DOWNLOAD QUEUE MANAGEMENT
    # ==========================================================================
    def _add_queue_widget(self, title, url):
        item = DownloadQueueItem(self.queue_frame, title, url)
        item.grid(row=len(self.download_queue_widgets), column=0, padx=5, pady=4, sticky="ew")
        self.download_queue_widgets.append(item)
        return item

    def _queue_smart_download(self, url):
        url = clean_url(url)
        if is_direct_file_url(url):
            filename = get_filename_from_url(url)
            self._queue_direct_download(url, filename)
        else:
            self._queue_ytdlp_download(
                url,
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                get_filename_from_url(url)
            )

    def _queue_ytdlp_download(self, url, format_string, title, is_mp3=False):
        """Queue a yt-dlp download with pause/resume/cancel support."""
        url = clean_url(url)
        dl_type = "MP3" if is_mp3 else "Video"
        queue_item = self._add_queue_widget(f"[{dl_type}] {title}", url)
        show_notification(f"{dl_type} Download Queued", f"{title[:40]}...")

        def _run():
            queue_item.update_status("⏳ Downloading...")
            save_dir = self.download_dir

            ydl_opts = {
                'format': format_string,
                'outtmpl': os.path.join(save_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [lambda d: self._ytdlp_progress_hook(d, queue_item)],
                'quiet': True,
                'no_warnings': True,
                'no_playlist': True,
            }

            if is_mp3:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                ydl_opts['merge_output_format'] = 'mp4'

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                if queue_item._ytdlp_cancelled:
                    self.after(0, queue_item.update_status, "❌ Cancelled")
                    return

                self.after(0, queue_item.mark_complete)
                self.after(0, self.update_status, f"Download complete: {title[:40]}...", 0)
                show_notification("Download Complete", f"{title[:40]}... saved!")
            except Exception as e:
                if queue_item._ytdlp_cancelled:
                    self.after(0, queue_item.update_status, "❌ Cancelled")
                    return
                self.after(0, queue_item.mark_failed, str(e)[:50])
                error_str = str(e)
                extra_msg = ""
                if "ffprobe" in error_str or "ffmpeg" in error_str:
                    extra_msg = "\n\nNote: For MP3, install 'ffmpeg' and add it to PATH."
                self.after(0, lambda: messagebox.showerror("Download Error", f"{e}{extra_msg}"))

        self.download_executor.submit(_run)

    def _queue_direct_download(self, url, filename, chunked=True):
        """Queue a direct file download with pause/resume/cancel."""
        mode = "Accelerated" if chunked else "Standard"
        queue_item = self._add_queue_widget(f"[{mode}] {filename}", url)
        show_notification("Download Queued", f"{filename}")

        def _run():
            save_path = os.path.join(self.download_dir, filename)

            base, ext = os.path.splitext(save_path)
            counter = 1
            while os.path.exists(save_path):
                save_path = f"{base}_{counter}{ext}"
                counter += 1

            def on_progress(downloaded, total):
                if total > 0:
                    pct = downloaded / total
                    mb_dl = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    speed_text = f"⏳ {mb_dl:.1f} / {mb_total:.1f} MB ({pct*100:.1f}%)"
                    self.after(0, queue_item.update_progress, pct)
                    self.after(0, queue_item.update_status, speed_text)
                    self.after(0, self.update_status, f"Downloading {filename}: {pct*100:.1f}%", pct)

            def on_status(text):
                self.after(0, queue_item.update_status, text)

            num_c = CHUNK_COUNT if chunked else 1
            downloader = ChunkedDownloader(
                url, save_path, num_chunks=num_c,
                progress_callback=on_progress, status_callback=on_status
            )
            queue_item.set_downloader(downloader)

            if chunked:
                success = downloader.download()
            else:
                success = downloader._single_stream_download()

            if success:
                self.after(0, queue_item.mark_complete)
                self.after(0, self.update_status, f"Saved: {os.path.basename(save_path)}", 0)
                show_notification("Download Complete", f"Saved: {os.path.basename(save_path)}")
            else:
                if downloader.cancelled:
                    self.after(0, queue_item.update_status, "❌ Cancelled")
                    # Clean up partial file
                    try:
                        if os.path.exists(save_path):
                            os.remove(save_path)
                    except OSError:
                        pass
                else:
                    self.after(0, queue_item.mark_failed, "Download failed")

        self.download_executor.submit(_run)

    def _ytdlp_progress_hook(self, d, queue_item):
        """yt-dlp progress hook with pause/cancel support."""
        # Check for cancel
        if queue_item._ytdlp_cancelled:
            raise Exception("Download cancelled by user")

        # Check for pause — block the download thread
        queue_item._pause_event.wait()

        if queue_item._ytdlp_cancelled:
            raise Exception("Download cancelled by user")

        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0.0%').replace('%', '').strip()
            percent_str = re.sub(r'\x1b\[[0-9;]*m', '', percent_str)
            try:
                percent = float(percent_str) / 100.0
            except ValueError:
                percent = 0.0

            speed = d.get('_speed_str', 'N/A')
            eta = d.get('_eta_str', 'N/A')
            speed = re.sub(r'\x1b\[[0-9;]*m', '', speed)
            eta = re.sub(r'\x1b\[[0-9;]*m', '', eta)

            status_text = f"⏳ {percent*100:.1f}% | {speed} | ETA: {eta}"
            self.after(0, queue_item.update_progress, percent)
            self.after(0, queue_item.update_status, status_text)
            self.after(0, self.update_status,
                       f"Downloading... {percent*100:.1f}% | {speed} | ETA: {eta}", percent)

        elif d['status'] == 'finished':
            self.after(0, queue_item.update_status, "🔄 Finalizing/Converting...")
            self.after(0, self.update_status, "Finalizing file...", 1.0)


# ==============================================================================
#  ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    app = AuraDownloaderPro()
    app.mainloop()
