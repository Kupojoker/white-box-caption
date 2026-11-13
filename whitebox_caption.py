"""
White Box Caption - local Windows app (iFunny / meme style captions)
Supports animated GIF, PNG/JPG/WebP images, and video (MP4/WebM/MOV/MKV via ffmpeg).
Default font: Impact (C:\\Windows\\Fonts\\impact.ttf) - or load any .ttf/.otf.
"""
import os, re, sys, shutil, subprocess, tempfile, threading
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageSequence, ImageTk

VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".flv", ".m4v"}
WIN_FONTS = r"C:\Windows\Fonts"

RES_CHOICES = ["Original",
               "Shorts / Reels / TikTok (1080x1920)", "Square (1080x1080)",
               "Portrait 4:5 (1080x1350)", "Landscape (1920x1080)", "Custom...",
               "1920 px wide", "1280 px wide", "854 px wide", "640 px wide", "480 px wide", "320 px wide"]
FIT_CHOICES = ["Fit (add bars)", "Fill (crop edges)", "Stretch"]
BAR_CHOICES = ["Blur", "Black", "White"]
QUALITY_CHOICES = ["Best", "High", "Medium", "Small", "Tiny"]
VID_CRF = {"Best": 18, "High": 23, "Medium": 28, "Small": 32, "Tiny": 36}   # lower = better/larger
GIF_COLORS = {"Best": 256, "High": 256, "Medium": 128, "Small": 64, "Tiny": 32}
JPG_Q = {"Best": 98, "High": 92, "Medium": 80, "Small": 65, "Tiny": 50}


def target_width(res, current_w):
    """Return the width to scale down to, or None to keep the original."""
    try:
        t = int(res.split()[0])
    except (ValueError, IndexError):
        return None
    return t if t < current_w else None


def resolve_output(res, cw, ch, cust_w, cust_h):
    """What to do with the output size: None, ("width", W) or ("box", W, H)."""
    if res.startswith("Custom"):
        W = max(2, int(cust_w)); H = max(0, int(cust_h))
        W -= W % 2; H -= H % 2
        return ("width", W) if H <= 0 else ("box", W, H)
    m = re.search(r"(\d+)x(\d+)", res)
    if m:
        return ("box", int(m.group(1)), int(m.group(2)))
    tw = target_width(res, cw)
    return ("width", tw) if tw else None


def apply_resize(img, mode, fit, bars):
    """PIL version of the resize / fit logic (used for preview, GIFs and images)."""
    if mode[0] == "width":
        tw = mode[1]
        th = max(2, round(img.height * tw / img.width))
        th -= th % 2
        return img.resize((tw, th), Image.LANCZOS)
    _, W, H = mode
    if fit.startswith("Stretch"):
        return img.resize((W, H), Image.LANCZOS)
    w, h = img.size
    if fit.startswith("Fill"):
        sc = max(W / w, H / h)
        r = img.resize((max(W, round(w * sc)), max(H, round(h * sc))), Image.LANCZOS)
        l, t = (r.width - W) // 2, (r.height - H) // 2
        return r.crop((l, t, l + W, t + H))
    sc = min(W / w, H / h)
    r = img.resize((max(1, round(w * sc)), max(1, round(h * sc))), Image.LANCZOS)
    if bars == "Blur":
        sw, sh = max(2, W // 8), max(2, H // 8)
        bg = apply_resize(img, ("box", sw, sh), "Fill", "Black")
        bg = bg.filter(ImageFilter.GaussianBlur(3)).resize((W, H), Image.BICUBIC)
    else:
        bg = Image.new("RGB", (W, H), "white" if bars == "White" else "black")
    bg.paste(r, ((W - r.width) // 2, (H - r.height) // 2))
    return bg


def ffmpeg_size_filter(mode, fit, bars):
    """ffmpeg filter chain fragment taking [o] and producing [v]."""
    if mode is None:
        return "[o]scale=trunc(iw/2)*2:trunc(ih/2)*2[v]"
    if mode[0] == "width":
        return f"[o]scale={mode[1]}:-2[v]"
    _, W, H = mode
    if fit.startswith("Stretch"):
        return f"[o]scale={W}:{H}[v]"
    if fit.startswith("Fill"):
        return f"[o]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[v]"
    fg = f"scale={W}:{H}:force_original_aspect_ratio=decrease:force_divisible_by=2"
    if bars == "Blur":
        return (f"[o]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=20:2[bg];[b]{fg}[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v]")
    color = "white" if bars == "White" else "black"
    return f"[o]{fg},pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={color}[v]"


def find_tool(name):
    """Find ffmpeg/ffprobe: PATH first, then next to the app / one folder up (incl. ffmpeg*/bin)."""
    p = shutil.which(name)
    if p:
        return p
    here = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    import glob
    for base in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        for pattern in (name + ".exe", os.path.join("bin", name + ".exe"),
                        os.path.join("ffmpeg*", "bin", name + ".exe"),
                        os.path.join("ffmpeg*", name + ".exe")):
            hits = glob.glob(os.path.join(base, pattern))
            if hits:
                return hits[0]
    return None


def find_default_font():
    for name in ("impact.ttf", "Impact.ttf", "IMPACT.TTF"):
        p = os.path.join(WIN_FONTS, name)
        if os.path.exists(p):
            return p
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        p = os.path.join(WIN_FONTS, name)
        if os.path.exists(p):
            return p
    return None


def load_font(path, size):
    try:
        if path:
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def wrap_text(text, font, max_w):
    lines = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for w in words:
            test = w if not cur else cur + " " + w
            if font.getlength(test) <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def render_box(width, s):
    """Render the caption box as an RGB image of the given width. s = settings dict."""
    pad = int(width * s["padding"] / 100.0)
    max_text_w = max(10, width - 2 * pad)
    size = s["font_size"]
    while True:
        font = load_font(s["font_path"], size)
        asc, desc = font.getmetrics()
        line_h = int((asc + desc) * 1.05)
        lines = wrap_text(s["text"], font, max_text_w)
        text_h = line_h * len(lines)
        if s["auto_height"]:
            box_h = text_h + 2 * pad
            break
        box_h = s["box_height"]
        if text_h + 2 * pad <= box_h or size <= 8:
            break
        size -= 2  # shrink to fit fixed-height box
    box_h = max(box_h, 2)
    box_h += box_h % 2  # even (video-friendly)

    img = Image.new("RGB", (width, box_h), s["bg"])
    d = ImageDraw.Draw(img)
    y = (box_h - text_h) // 2
    for line in lines:
        lw = font.getlength(line)
        if s["align"] == "Left":
            x = pad
        elif s["align"] == "Right":
            x = width - pad - lw
        else:
            x = (width - lw) / 2
        d.text((x, y), line, font=font, fill=s["fg"], anchor="la")
        y += line_h
    if s["border"] > 0:
        b = s["border"]
        if s["position"] == "Top":
            d.rectangle([0, box_h - b, width, box_h], fill="black")
        else:
            d.rectangle([0, 0, width, b - 1], fill="black")
    return img


def compose(frame, box, position):
    w, h = frame.size
    out = Image.new("RGB", (w, h + box.height), "white")
    if position == "Top":
        out.paste(box, (0, 0))
        out.paste(frame.convert("RGB"), (0, box.height))
    else:
        out.paste(frame.convert("RGB"), (0, 0))
        out.paste(box, (0, h))
    return out


def ffprobe_size(path):
    r = subprocess.run(
        [find_tool("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    w, h = r.stdout.strip().split("x")
    return int(w), int(h)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("White Box Caption")
        self.geometry("1000x860")
        self.src_path = None
        self.is_video = False
        self.preview_src = None  # PIL image used for preview (first frame)
        self.tk_img = None
        self.font_path = find_default_font()
        self.fg = "#000000"
        self.bg = "#ffffff"
        self.build_ui()
        if not self.font_path or "impact" not in self.font_path.lower():
            self.status.set("Impact not found - using fallback font. Use 'Load font' to pick one.")

    # ---------- UI ----------
    def build_ui(self):
        left = ttk.Frame(self, padding=8)
        left.pack(side="left", fill="y")
        right = ttk.Frame(self, padding=8)
        right.pack(side="right", fill="both", expand=True)

        ttk.Button(left, text="Open GIF / image / video...", command=self.open_file).pack(fill="x")
        self.file_lbl = ttk.Label(left, text="No file loaded", wraplength=260)
        self.file_lbl.pack(fill="x", pady=(2, 8))

        ttk.Label(left, text="Caption text:").pack(anchor="w")
        self.text = tk.Text(left, width=34, height=5, wrap="word")
        self.text.pack(fill="x")
        self.text.insert("1.0", "when the caption is\nin Impact")
        self.text.bind("<<Modified>>", self.on_text_mod)

        grid = ttk.Frame(left)
        grid.pack(fill="x", pady=8)
        self.v_font_size = tk.IntVar(value=40)
        self.v_padding = tk.DoubleVar(value=4)
        self.v_border = tk.IntVar(value=0)
        self.v_box_h = tk.IntVar(value=120)
        self.v_auto = tk.BooleanVar(value=True)
        self.v_align = tk.StringVar(value="Center")
        self.v_pos = tk.StringVar(value="Top")

        def row(r, label, widget):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w", pady=2)
            widget.grid(row=r, column=1, sticky="we", pady=2, padx=(6, 0))

        def spin(var, lo, hi, inc=1):
            sp = ttk.Spinbox(grid, from_=lo, to=hi, increment=inc, textvariable=var, width=8,
                             command=self.refresh)
            sp.bind("<KeyRelease>", lambda e: self.refresh())
            return sp

        row(0, "Font size (px):", spin(self.v_font_size, 8, 200))
        row(1, "Padding (% width):", spin(self.v_padding, 0, 30, 0.5))
        row(2, "Black border (px):", spin(self.v_border, 0, 20))
        row(3, "Box height (px):", spin(self.v_box_h, 20, 1000))
        c = ttk.Checkbutton(grid, text="Auto height", variable=self.v_auto, command=self.refresh)
        c.grid(row=4, column=1, sticky="w")
        al = ttk.Combobox(grid, textvariable=self.v_align, values=["Left", "Center", "Right"],
                          state="readonly", width=8)
        al.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        row(5, "Align:", al)
        po = ttk.Combobox(grid, textvariable=self.v_pos, values=["Top", "Bottom"],
                          state="readonly", width=8)
        po.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        row(6, "Position:", po)

        fr = ttk.Frame(left)
        fr.pack(fill="x")
        self.font_lbl = ttk.Label(fr, text=self.font_name(), wraplength=260)
        self.font_lbl.pack(anchor="w")
        ttk.Button(fr, text="Load font (.ttf/.otf)...", command=self.pick_font).pack(fill="x", pady=2)

        cf = ttk.Frame(left)
        cf.pack(fill="x", pady=6)
        self.fg_btn = tk.Button(cf, text="Text color", bg=self.fg, fg="white", command=self.pick_fg)
        self.fg_btn.pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.bg_btn = tk.Button(cf, text="Box color", bg=self.bg, fg="black", command=self.pick_bg)
        self.bg_btn.pack(side="left", expand=True, fill="x", padx=(3, 0))

        of = ttk.LabelFrame(left, text="Output", padding=6)
        of.pack(fill="x", pady=(6, 0))
        self.v_res = tk.StringVar(value="Original")
        self.v_quality = tk.StringVar(value="High")
        self.v_fit = tk.StringVar(value=FIT_CHOICES[0])
        self.v_bars = tk.StringVar(value=BAR_CHOICES[0])
        self.v_cw = tk.IntVar(value=1080)
        self.v_ch = tk.IntVar(value=1920)

        ttk.Label(of, text="Resolution:").grid(row=0, column=0, sticky="w", pady=2)
        res_cb = ttk.Combobox(of, textvariable=self.v_res, values=RES_CHOICES, state="readonly", width=24)
        res_cb.grid(row=0, column=1, columnspan=3, sticky="we", padx=(6, 0))
        res_cb.bind("<<ComboboxSelected>>", lambda e: self.on_res_change())

        ttk.Label(of, text="Custom W x H:").grid(row=1, column=0, sticky="w", pady=2)
        self.cw_sp = ttk.Spinbox(of, from_=2, to=8000, increment=2, textvariable=self.v_cw, width=6,
                                 command=self.refresh, state="disabled")
        self.cw_sp.grid(row=1, column=1, padx=(6, 0), sticky="w")
        ttk.Label(of, text="x").grid(row=1, column=2)
        self.ch_sp = ttk.Spinbox(of, from_=0, to=8000, increment=2, textvariable=self.v_ch, width=6,
                                 command=self.refresh, state="disabled")
        self.ch_sp.grid(row=1, column=3, sticky="w")
        for sp in (self.cw_sp, self.ch_sp):
            sp.bind("<KeyRelease>", lambda e: self.refresh())

        ttk.Label(of, text="Fit:").grid(row=2, column=0, sticky="w", pady=2)
        fit_cb = ttk.Combobox(of, textvariable=self.v_fit, values=FIT_CHOICES, state="readonly", width=24)
        fit_cb.grid(row=2, column=1, columnspan=3, sticky="we", padx=(6, 0))
        fit_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Label(of, text="Bars:").grid(row=3, column=0, sticky="w", pady=2)
        bar_cb = ttk.Combobox(of, textvariable=self.v_bars, values=BAR_CHOICES, state="readonly", width=24)
        bar_cb.grid(row=3, column=1, columnspan=3, sticky="we", padx=(6, 0))
        bar_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Label(of, text="Compression:").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Combobox(of, textvariable=self.v_quality, values=QUALITY_CHOICES, state="readonly",
                     width=24).grid(row=4, column=1, columnspan=3, sticky="we", padx=(6, 0))
        ttk.Label(of, text="Fit/Bars apply to exact sizes (Shorts, Square, Custom).\n"
                           "Custom height 0 = auto. 'Fill' crops and can cut the caption.\n"
                           "Compression: video quality / GIF colors / JPG quality.",
                  foreground="#666", wraplength=270).grid(row=5, column=0, columnspan=4, sticky="w", pady=(4, 0))

        ttk.Button(left, text="Save...", command=self.save).pack(fill="x", pady=(10, 2))
        self.progress = ttk.Progressbar(left, mode="indeterminate")
        self.progress.pack(fill="x", pady=2)
        self.status = tk.StringVar(value="Open a file to begin.")
        ttk.Label(left, textvariable=self.status, wraplength=260, foreground="#555").pack(fill="x")

        self.canvas = tk.Canvas(right, bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.refresh())

    def font_name(self):
        return "Font: " + (os.path.basename(self.font_path) if self.font_path else "(default)")

    def on_res_change(self):
        state = "normal" if self.v_res.get().startswith("Custom") else "disabled"
        self.cw_sp.config(state=state)
        self.ch_sp.config(state=state)
        self.refresh()

    def on_text_mod(self, _):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.refresh()

    def pick_font(self):
        p = filedialog.askopenfilename(title="Choose font",
                                       initialdir=WIN_FONTS if os.path.isdir(WIN_FONTS) else None,
                                       filetypes=[("Fonts", "*.ttf *.otf"), ("All", "*.*")])
        if p:
            self.font_path = p
            self.font_lbl.config(text=self.font_name())
            self.refresh()

    def pick_fg(self):
        c = colorchooser.askcolor(color=self.fg)[1]
        if c:
            self.fg = c
            self.fg_btn.config(bg=c)
            self.refresh()

    def pick_bg(self):
        c = colorchooser.askcolor(color=self.bg)[1]
        if c:
            self.bg = c
            self.bg_btn.config(bg=c)
            self.refresh()

    # ---------- Logic ----------
    def settings(self):
        def num(v, default):
            try:
                return v.get()
            except tk.TclError:
                return default
        return dict(
            text=self.text.get("1.0", "end-1c") or " ",
            font_path=self.font_path,
            font_size=num(self.v_font_size, 40),
            padding=num(self.v_padding, 4),
            border=num(self.v_border, 0),
            box_height=num(self.v_box_h, 120),
            auto_height=self.v_auto.get(),
            align=self.v_align.get(),
            position=self.v_pos.get(),
            fg=self.fg, bg=self.bg,
            res=self.v_res.get(), quality=self.v_quality.get(),
            fit=self.v_fit.get(), bars=self.v_bars.get(),
            custom_w=num(self.v_cw, 1080), custom_h=num(self.v_ch, 1920),
        )

    def open_file(self):
        p = filedialog.askopenfilename(
            filetypes=[("Media", "*.gif *.png *.jpg *.jpeg *.webp *.bmp *.mp4 *.webm *.mov *.mkv *.avi *.flv *.m4v"),
                       ("All", "*.*")])
        if not p:
            return
        ext = os.path.splitext(p)[1].lower()
        try:
            if ext in VIDEO_EXT:
                if not find_tool("ffmpeg") or not find_tool("ffprobe"):
                    messagebox.showerror("ffmpeg missing",
                                         "Video support needs ffmpeg.exe and ffprobe.exe.\nPut the ffmpeg folder next to this app (or add its bin folder to PATH) and restart.")
                    return
                self.is_video = True
                w, h = ffprobe_size(p)
                tmp = os.path.join(tempfile.gettempdir(), "wbc_frame.png")
                subprocess.run([find_tool("ffmpeg"), "-y", "-v", "error", "-i", p, "-frames:v", "1", tmp],
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
                self.preview_src = Image.open(tmp).convert("RGB")
            else:
                self.is_video = False
                im = Image.open(p)
                self.preview_src = im.convert("RGB")
        except Exception as e:
            messagebox.showerror("Error", f"Couldn't open file:\n{e}")
            return
        self.src_path = p
        self.file_lbl.config(text=os.path.basename(p))
        self.status.set(f"{self.preview_src.width}x{self.preview_src.height}")
        self.refresh()

    def refresh(self):
        if self.preview_src is None:
            return
        s = self.settings()
        box = render_box(self.preview_src.width, s)
        out = compose(self.preview_src, box, s["position"])
        mode = resolve_output(s["res"], out.width, out.height, s["custom_w"], s["custom_h"])
        if mode:
            out = apply_resize(out, mode, s["fit"], s["bars"])
        cw, ch = max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)
        scale = min(cw / out.width, ch / out.height, 1.0)
        disp = out.resize((max(1, int(out.width * scale)), max(1, int(out.height * scale))), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self.tk_img)

    def save(self):
        if not self.src_path:
            messagebox.showinfo("Nothing loaded", "Open a file first.")
            return
        base, ext = os.path.splitext(self.src_path)
        ext = ext.lower()
        if self.is_video:
            types, default = [("Video", "*" + ext)], ext
        elif ext == ".gif":
            types, default = [("GIF", "*.gif")], ".gif"
        else:
            types, default = [("PNG", "*.png"), ("JPEG", "*.jpg")], ".png"
        out = filedialog.asksaveasfilename(initialfile=os.path.basename(base) + "_caption" + default,
                                           defaultextension=default, filetypes=types)
        if not out:
            return
        s = self.settings()
        self.progress.start(10)
        self.status.set("Processing...")
        threading.Thread(target=self._work, args=(out, s), daemon=True).start()

    def _work(self, out, s):
        try:
            if self.is_video:
                self._save_video(out, s)
            else:
                self._save_image(out, s)
            self.after(0, lambda: self._done(f"Saved: {out}"))
        except Exception as e:
            self.after(0, lambda: self._done(f"Error: {e}", True))

    def _done(self, msg, err=False):
        self.progress.stop()
        self.status.set(msg)
        if err:
            messagebox.showerror("Error", msg)

    def _save_image(self, out, s):
        im = Image.open(self.src_path)
        box = render_box(im.width, s)
        frames, durs = [], []
        for fr in ImageSequence.Iterator(im):
            durs.append(fr.info.get("duration", im.info.get("duration", 100)))
            frames.append(compose(fr.convert("RGBA").convert("RGB"), box, s["position"]))
        mode = resolve_output(s["res"], frames[0].width, frames[0].height, s["custom_w"], s["custom_h"])
        if mode:
            frames = [apply_resize(f, mode, s["fit"], s["bars"]) for f in frames]
        if out.lower().endswith(".gif"):
            colors = GIF_COLORS.get(s["quality"], 256)
            frames = [f.convert("P", palette=Image.ADAPTIVE, colors=colors) for f in frames]
            if len(frames) == 1:
                frames[0].save(out, optimize=True)
            else:
                frames[0].save(out, save_all=True, append_images=frames[1:], duration=durs,
                               loop=im.info.get("loop", 0), disposal=2, optimize=True)
        elif out.lower().endswith((".jpg", ".jpeg")):
            frames[0].save(out, quality=JPG_Q.get(s["quality"], 92))
        else:
            frames[0].save(out)

    def _save_video(self, out, s):
        w, h = ffprobe_size(self.src_path)
        box = render_box(w, s)
        box_png = os.path.join(tempfile.gettempdir(), "wbc_box.png")
        box.save(box_png)
        bh = box.height
        if s["position"] == "Top":
            filt = f"[0:v]pad=iw:ih+{bh}:0:{bh}:color=white[p];[p][1:v]overlay=0:0[o]"
        else:
            filt = f"[0:v]pad=iw:ih+{bh}:0:0:color=white[p];[p][1:v]overlay=0:{h}[o]"
        mode = resolve_output(s["res"], w, h + bh, s["custom_w"], s["custom_h"])
        filt += ";" + ffmpeg_size_filter(mode, s["fit"], s["bars"])
        crf = str(VID_CRF.get(s["quality"], 23))
        if out.lower().endswith(".webm"):
            codec = ["-c:v", "libvpx-vp9", "-crf", crf, "-b:v", "0", "-c:a", "libopus"]
        else:
            codec = ["-c:v", "libx264", "-crf", crf, "-preset", "medium", "-pix_fmt", "yuv420p",
                     "-c:a", "aac", "-b:a", "128k"]
            if out.lower().endswith((".mp4", ".mov", ".m4v")):
                codec += ["-movflags", "+faststart"]
        cmd = [find_tool("ffmpeg"), "-y", "-v", "error", "-i", self.src_path, "-i", box_png,
               "-filter_complex", filt, "-map", "[v]", "-map", "0:a?"] + codec + [out]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-400:])


if __name__ == "__main__":
    App().mainloop()
