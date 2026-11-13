# White Box Caption

A small offline Windows app for adding **iFunny / meme-style white box captions** to GIFs, images and videos, with **Impact** (or any font you load).

Inspired by the white box caption tool on ezgif.com. This project is not affiliated with ezgif.
## Features

- Animated GIF, PNG, JPG, WebP and video (MP4, WebM, MOV, MKV)
- Impact font by default (uses the copy that ships with Windows), or load any `.ttf` / `.otf`
- Live preview
- Text, box color, text color, font size, padding %, black border, box height (or auto height)
- Left / center / right alignment, caption on top or bottom
- **Output resolution**: presets for Shorts / Reels / TikTok (1080x1920), Square, 4:5 and Landscape, a **Custom width x height** option, or scale to a set width. Choose **Fit** (with blurred, black or white bars), **Fill** (crop) or **Stretch**
- **Compression** presets (Best to Tiny): H.264 or VP9 quality for video, reduced color palette for GIFs, JPEG quality for JPGs
- Everything runs locally. No uploads, no watermarks, no file size limits

## Download

Grab `WhiteBoxCaption.exe` from the [Releases page](../../releases/latest). No Python needed.

> Windows may show a SmartScreen warning for unsigned apps. Click **More info → Run anyway**.

## Video support (optional)

GIFs and images work out of the box. Video needs **ffmpeg**:

1. Download the "release essentials" build from <https://www.gyan.dev/ffmpeg/builds/> and extract it.
2. Put the extracted `ffmpeg-...` folder **next to `WhiteBoxCaption.exe`** (or one folder up), or add its `bin` folder to your PATH.
3. Make sure `bin` contains both `ffmpeg.exe` and `ffprobe.exe`.

## Run from source

```
pip install -r requirements.txt
python whitebox_caption.py
```

Or double-click `run.bat`. To build your own exe, run `build_exe.bat`.

Requires Python 3.9+ with Tkinter (included in the standard Windows installer).

## Notes

- Impact is a Microsoft font and is not bundled. The app reads it from `C:\Windows\Fonts`.
- ffmpeg is not bundled either; it is a separate project with its own license.

## License
KupoJoker

Latest download
https://github.com/Kupojoker/white-box-caption/releases/tag/v1.3.0

## Acknowledgments & Contributors

- **KupoJoker** - Lead Developer / Creator
- **Gemini (Google)** - Core architecture, UI refinements, and feature implementation
- **Claude (Anthropic)** - Code review, architectural analysis, and debugging support
