# Video Enhancement Suite

This workspace contains two Streamlit apps:

- `videoenhancer.py`: main video editing and enhancement app.
- `qualitycheck.py`: quality/readiness checker for uploaded MP4 videos.

The tools are designed for local processing on your machine.

## Features

### 1. Video Enhancer (`videoenhancer.py`)

- MP4 upload and metadata display (duration, FPS, resolution).
- Optional watermark removal workflow:
   - blur/pixelate effect
   - auto-detect watermark area
   - manual X/Y/width/height controls with arrow buttons
- Main watermark text styling:
   - many fonts
   - regular/bold/italic/bold-italic
   - size and opacity
   - strong black shadow
- Additional text overlay system:
   - custom text content
   - font, style, color, size, opacity
   - optional black shadow
   - optional background box (color/opacity/padding/rounded)
   - preset positions + custom X/Y
- Quality controls:
   - output FPS selector
   - 4K / 8K / 12K output levels
   - render speed profiles (Balanced / Fast / Maximum Speed)
- Recommendation-focused options:
   - auto quality fixes
   - dynamic motion effect
   - optional creative intro label
   - optional narration audio mix (mp3/wav/m4a)
   - minimum-duration extension
- Auto Quality Report panel with pass/warn indicators.
- Processing progress bar and status text.
- Estimated output size (from uploaded file characteristics).
- Final enhanced video preview + download button + actual output storage metric.

### 2. Quality Checker (`qualitycheck.py`)

- MP4 upload and playback.
- Automated checks for:
   - duration
   - resolution
   - FPS
   - static/low-motion behavior
- Manual originality checklist.
- Combined score and improvement suggestions.

## Requirements

- Python 3.9+
- FFmpeg available (installed system-wide or via `imageio-ffmpeg` package)

## Installation

```bash
pip install -r requirements.txt
```

## Run

### Main enhancer app

```bash
streamlit run videoenhancer.py
```

### Quality checker app

```bash
streamlit run qualitycheck.py
```

Streamlit will print a local URL (usually `http://localhost:8501`).

## Typical Workflow

1. Open `videoenhancer.py`.
2. Upload your MP4.
3. Configure watermark removal (optional).
4. Configure text overlays and styling.
5. Choose FPS, enhancement level, and render speed.
6. (Optional) enable Auto Quality Fixes and narration.
7. Check the Auto Quality Report.
8. Process and download the enhanced output.
9. (Optional) validate in `qualitycheck.py`.

## Performance Notes

- 8K/12K, high FPS, and long videos are compute-intensive.
- Use `Render Speed = Fast` or `Maximum Speed` for shorter export times.
- Reducing FPS and/or output resolution significantly reduces render time.

## Troubleshooting

- If encoding fails, verify dependencies:
   - `streamlit`, `moviepy`, `opencv-python`, `pillow`, `imageio-ffmpeg`
- If fonts are not applied exactly, ensure the chosen font exists in Windows Fonts.
- If processing is slow, lower one or more of: resolution, FPS, duration, quality profile.

## File Overview

```text
.
├── videoenhancer.py
├── qualitycheck.py
├── requirements.txt
└── README.md
```
