import streamlit as st
import cv2
import numpy as np
from moviepy.editor import VideoFileClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
from PIL import Image, ImageDraw, ImageFont
import tempfile
import os
from pathlib import Path
import html
import subprocess
import imageio_ffmpeg

st.set_page_config(layout="wide", page_title="Video Enhancement Tool")

st.title("🎬 Video Enhancement Tool")
st.markdown("Enhance your videos with custom watermarks and watermark removal effects")

# Create sidebar for controls
st.sidebar.header("Configuration")

# Initialize session state for area selection
if 'selected_area' not in st.session_state:
    st.session_state.selected_area = None
if 'video_file' not in st.session_state:
    st.session_state.video_file = None
if 'remove_watermark' not in st.session_state:
    st.session_state.remove_watermark = True

FONT_OPTIONS = [
    "Brush Script MT",
    "Segoe Script",
    "Lucida Handwriting",
    "Comic Sans MS",
    "Arial",
    "Calibri",
    "Verdana",
    "Trebuchet MS",
    "Tahoma",
    "Georgia",
    "Times New Roman",
    "Garamond",
    "Courier New",
    "Impact",
    "System Default"
]

FONT_STYLE_OPTIONS = ["Regular", "Bold", "Italic", "Bold Italic"]

FONT_FILE_CANDIDATES = {
    "Brush Script MT": ["BRUSHSCI.TTF", "brushsci.ttf"],
    "Segoe Script": ["SEGOESC.TTF", "segoesc.ttf"],
    "Lucida Handwriting": ["LHANDW.TTF", "lhandw.ttf"],
    "Comic Sans MS": ["COMIC.TTF", "comic.ttf", "comicbd.ttf"],
    "Arial": ["ARIAL.TTF", "arial.ttf"],
    "Calibri": ["CALIBRI.TTF", "calibri.ttf"],
    "Verdana": ["VERDANA.TTF", "verdana.ttf"],
    "Trebuchet MS": ["TREBUC.TTF", "trebuc.ttf"],
    "Tahoma": ["TAHOMA.TTF", "tahoma.ttf"],
    "Georgia": ["GEORGIA.TTF", "georgia.ttf"],
    "Times New Roman": ["TIMES.TTF", "times.ttf"],
    "Garamond": ["GARA.TTF", "gara.ttf"],
    "Courier New": ["COUR.TTF", "cour.ttf"],
    "Impact": ["IMPACT.TTF", "impact.ttf"],
    "System Default": []
}


def resolve_font_path(font_name):
    candidates = FONT_FILE_CANDIDATES.get(font_name, [])
    if not candidates:
        return None

    windows_dir = os.environ.get("WINDIR", "C:/Windows")
    font_dirs = [
        os.path.join(windows_dir, "Fonts"),
        os.path.join(windows_dir, "fonts")
    ]

    for candidate in candidates:
        if os.path.isabs(candidate) and os.path.exists(candidate):
            return candidate
        for font_dir in font_dirs:
            full_path = os.path.join(font_dir, candidate)
            if os.path.exists(full_path):
                return full_path
    return None


def load_font(font_name, font_size):
    font_path = resolve_font_path(font_name)
    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except OSError:
            pass

    # Keep size increments working with a scalable fallback font.
    try:
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except OSError:
        return ImageFont.load_default()


def get_text_size(draw, text, font, font_style):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Italic skew needs extra horizontal room.
    if "Italic" in font_style:
        text_width = int(text_width * 1.2)
    return text_width, text_height


def draw_styled_watermark(overlay, text, font, text_x, text_y, alpha, font_style):
    shadow_alpha = max(120, int(alpha * 0.75))
    shadow_offsets = [(2, 2), (3, 2), (2, 3)]
    is_bold = "Bold" in font_style
    is_italic = "Italic" in font_style

    if not is_italic:
        draw = ImageDraw.Draw(overlay)
        for ox, oy in shadow_offsets:
            draw.text((text_x + ox, text_y + oy), text, fill=(0, 0, 0, shadow_alpha), font=font)

        if is_bold:
            # Fake bold by painting neighboring pixels.
            bold_offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]
            for ox, oy in bold_offsets:
                draw.text((text_x + ox, text_y + oy), text, fill=(255, 255, 255, alpha), font=font)
        else:
            draw.text((text_x, text_y), text, fill=(255, 255, 255, alpha), font=font)
        return

    # For italic, draw into a temp layer and shear it.
    temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1), (0, 0, 0, 0)))
    base_w, base_h = get_text_size(temp_draw, text, font, "Regular")
    text_layer = Image.new('RGBA', (base_w + 12, base_h + 10), (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(text_layer)

    for ox, oy in shadow_offsets:
        layer_draw.text((ox, oy), text, fill=(0, 0, 0, shadow_alpha), font=font)
    if is_bold:
        for ox, oy in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            layer_draw.text((ox, oy), text, fill=(255, 255, 255, alpha), font=font)
    else:
        layer_draw.text((0, 0), text, fill=(255, 255, 255, alpha), font=font)

    skew = -0.35
    skewed_width = int(text_layer.width + abs(skew) * text_layer.height)
    skewed = text_layer.transform(
        (skewed_width, text_layer.height),
        Image.AFFINE,
        (1, skew, 0, 0, 1, 0),
        resample=Image.BICUBIC
    )
    overlay.alpha_composite(skewed, (text_x, text_y))


def hex_to_rgb(hex_color):
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return (255, 255, 255)
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def compute_text_position(frame_w, frame_h, text_w, text_h, preset, x_pct=50, y_pct=50, pad=24):
    if preset == "Top Left":
        x, y = pad, pad
    elif preset == "Top Right":
        x, y = frame_w - text_w - pad, pad
    elif preset == "Center":
        x, y = (frame_w - text_w) // 2, (frame_h - text_h) // 2
    elif preset == "Bottom Left":
        x, y = pad, frame_h - text_h - pad
    elif preset == "Bottom Right":
        x, y = frame_w - text_w - pad, frame_h - text_h - pad
    else:
        x = int((frame_w - text_w) * (x_pct / 100.0))
        y = int((frame_h - text_h) * (y_pct / 100.0))

    x = max(0, min(x, frame_w - text_w - 1))
    y = max(0, min(y, frame_h - text_h - 1))
    return x, y


def draw_styled_text(overlay, text, font, text_x, text_y, text_rgba, font_style, shadow_enabled=True):
    shadow_alpha = max(90, int(text_rgba[3] * 0.7)) if shadow_enabled else 0
    shadow_offsets = [(2, 2), (3, 2), (2, 3)]
    is_bold = "Bold" in font_style
    is_italic = "Italic" in font_style

    if not is_italic:
        draw = ImageDraw.Draw(overlay)
        if shadow_enabled:
            for ox, oy in shadow_offsets:
                draw.text((text_x + ox, text_y + oy), text, fill=(0, 0, 0, shadow_alpha), font=font)

        if is_bold:
            for ox, oy in [(0, 0), (1, 0), (0, 1), (1, 1)]:
                draw.text((text_x + ox, text_y + oy), text, fill=text_rgba, font=font)
        else:
            draw.text((text_x, text_y), text, fill=text_rgba, font=font)
        return

    temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1), (0, 0, 0, 0)))
    base_w, base_h = get_text_size(temp_draw, text, font, "Regular")
    text_layer = Image.new('RGBA', (base_w + 12, base_h + 10), (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(text_layer)

    if shadow_enabled:
        for ox, oy in shadow_offsets:
            layer_draw.text((ox, oy), text, fill=(0, 0, 0, shadow_alpha), font=font)
    if is_bold:
        for ox, oy in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            layer_draw.text((ox, oy), text, fill=text_rgba, font=font)
    else:
        layer_draw.text((0, 0), text, fill=text_rgba, font=font)

    skew = -0.35
    skewed_width = int(text_layer.width + abs(skew) * text_layer.height)
    skewed = text_layer.transform(
        (skewed_width, text_layer.height),
        Image.AFFINE,
        (1, skew, 0, 0, 1, 0),
        resample=Image.BICUBIC
    )
    overlay.alpha_composite(skewed, (text_x, text_y))


def render_font_preview_block(selected_font, text_size, font_style):
    css_weight = "700" if "Bold" in font_style else "400"
    css_style = "italic" if "Italic" in font_style else "normal"
    preview_lines = []
    for font_name in FONT_OPTIONS:
        safe_font_name = html.escape(font_name)
        sample = f"{font_name} ({font_style}) - The quick brown fox"
        safe_sample = html.escape(sample)
        border = "2px solid #2aa198" if font_name == selected_font else "1px solid #d0d7de"
        bg = "rgba(42,161,152,0.1)" if font_name == selected_font else "rgba(255,255,255,0.0)"
        preview_lines.append(
            f"<div style=\"font-family:'{safe_font_name}', sans-serif; font-size:{text_size}px; "
            f"font-weight:{css_weight}; font-style:{css_style}; margin:6px 0; padding:6px 8px; "
            f"border-radius:6px; border:{border}; background:{bg};\">"
            f"{safe_sample}</div>"
        )

    return "".join(preview_lines)


def estimate_output_size_mb(input_bytes, duration_seconds, source_long_edge, target_long_edge, source_fps, target_fps):
    # Estimate output size from the uploaded file's actual bitrate, then scale it
    # upward for higher target resolutions with a floor for each enhancement level.
    if duration_seconds <= 0 or input_bytes <= 0:
        return 0.0

    source_bitrate_mbps = (input_bytes * 8.0 / duration_seconds) / 1_000_000.0
    target_floor_mbps = {
        3840: 30,
        7680: 85,
        11520: 170
    }[target_long_edge]

    resolution_scale = max(1.0, target_long_edge / max(source_long_edge, 1)) ** 1.15
    fps_scale = max(target_fps, 1.0) / max(source_fps, 1.0)
    estimated_video_bitrate_mbps = max(target_floor_mbps, source_bitrate_mbps * resolution_scale * fps_scale)
    audio_bitrate_mbps = 0.192  # AAC ~192 kbps
    total_megabits = (estimated_video_bitrate_mbps + audio_bitrate_mbps) * duration_seconds
    return total_megabits / 8.0

# File upload
uploaded_file = st.sidebar.file_uploader(
    "Upload Video",
    type=["mp4", "mov", "m4v", "webm", "avi", "mkv", "3gp"]
)
st.sidebar.caption("Tip: Phone videos are often .mov/.m4v/.3gp. If a file still fails, convert it to MP4 (H.264).")

if uploaded_file:
    st.session_state.video_file = uploaded_file
    
    # Display video info
    video_bytes = uploaded_file.getvalue()
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_file:
        tmp_file.write(video_bytes)
        temp_video_path = tmp_file.name
    
    # Load video info
    video_clip = VideoFileClip(temp_video_path)
    duration = video_clip.duration
    fps = video_clip.fps
    size = video_clip.size
    input_file_size_bytes = len(video_bytes)
    
    st.sidebar.info(f"📊 Video Info:\n- Duration: {duration:.2f}s\n- FPS: {fps}\n- Resolution: {size[0]}x{size[1]}")

    # Output FPS selection
    st.sidebar.subheader("Output FPS")
    common_fps_values = [24, 25, 30, 48, 50, 60, 90, 120]
    fps_options = []
    source_fps_rounded = int(round(fps)) if fps else 30
    if source_fps_rounded not in common_fps_values:
        fps_options.append(source_fps_rounded)
    fps_options.extend([value for value in common_fps_values if value not in fps_options])
    output_fps = st.sidebar.selectbox("Select output FPS", fps_options, index=fps_options.index(source_fps_rounded) if source_fps_rounded in fps_options else 0)
    
    # Watermark text input
    watermark_text = st.sidebar.text_input("Enter Watermark Text", value="WATERMARK")

    st.sidebar.subheader("Additional Text Overlay")
    add_custom_text = st.sidebar.toggle("Add extra text", value=False)
    custom_text = ""
    custom_font = "Arial"
    custom_font_style = "Regular"
    custom_text_size = 28
    custom_text_color = "#FFFFFF"
    custom_text_opacity = 90
    custom_shadow = True
    custom_bg_enabled = False
    custom_bg_color = "#000000"
    custom_bg_opacity = 55
    custom_bg_padding = 12
    custom_bg_rounded = True
    custom_position = "Bottom Right"
    custom_x_pct = 50
    custom_y_pct = 50

    if add_custom_text:
        custom_text = st.sidebar.text_area("Text to add", value="New text overlay")

        custom_col1, custom_col2 = st.sidebar.columns(2)
        with custom_col1:
            custom_font = st.selectbox("Text font", FONT_OPTIONS, index=4)
            custom_font_style = st.selectbox("Text style", FONT_STYLE_OPTIONS, index=0)
            custom_text_size = st.slider("Text size", 10, 96, 28)
            custom_text_opacity = st.slider("Text opacity (%)", 10, 100, 90)
        with custom_col2:
            custom_text_color = st.color_picker("Text color", "#FFFFFF")
            custom_shadow = st.toggle("Black shadow", value=True)
            custom_position = st.selectbox(
                "Text position",
                ["Top Left", "Top Right", "Center", "Bottom Left", "Bottom Right", "Custom"]
            )
            if custom_position == "Custom":
                custom_x_pct = st.slider("Text X position (%)", 0, 100, 50)
                custom_y_pct = st.slider("Text Y position (%)", 0, 100, 50)

        custom_bg_enabled = st.sidebar.toggle("Text background", value=False)
        if custom_bg_enabled:
            bg_col1, bg_col2 = st.sidebar.columns(2)
            with bg_col1:
                custom_bg_color = st.color_picker("Background color", "#000000")
                custom_bg_opacity = st.slider("Background opacity (%)", 0, 100, 55)
            with bg_col2:
                custom_bg_padding = st.slider("Background padding", 0, 40, 12)
                custom_bg_rounded = st.toggle("Rounded background", value=True)
    
    # Watermark styling
    st.sidebar.subheader("Watermark Style")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        font_choice = st.selectbox("Font", FONT_OPTIONS)
        text_size = st.slider("Text Size", 8, 40, 16, step=1)
    with col2:
        font_style = st.selectbox("Font Style", FONT_STYLE_OPTIONS)
        opacity = st.slider("Opacity (%)", 30, 100, 80)

    st.sidebar.subheader("Render Speed")
    render_speed = st.sidebar.selectbox(
        "Speed / Quality Mode",
        ["Balanced", "Fast", "Maximum Speed"],
        index=1
    )

    render_profile = {
        "Balanced": {"moviepy_preset": "medium", "ffmpeg_preset": "medium", "crf": "18"},
        "Fast": {"moviepy_preset": "veryfast", "ffmpeg_preset": "veryfast", "crf": "21"},
        "Maximum Speed": {"moviepy_preset": "ultrafast", "ffmpeg_preset": "ultrafast", "crf": "24"},
    }[render_speed]

    st.sidebar.subheader("Recommendation Quality Fixes")
    auto_quality_fixes = st.sidebar.toggle("Auto quality fixes", value=True)

    dynamic_motion = False
    add_creative_intro = False
    minimum_duration_target = 8
    narration_file = None
    if auto_quality_fixes:
        dynamic_motion = st.sidebar.toggle("Keep video dynamic", value=True)
        add_creative_intro = st.sidebar.toggle("Add creative intro edit", value=True)
        minimum_duration_target = st.sidebar.slider("Minimum duration target (seconds)", 8, 60, 12)
        narration_file = st.sidebar.file_uploader(
            "Optional narration audio (mp3/wav/m4a)",
            type=["mp3", "wav", "m4a"],
            key="narration_uploader"
        )

    effective_output_fps = max(output_fps, 30) if auto_quality_fixes else output_fps
    if effective_output_fps != output_fps:
        st.sidebar.caption(f"FPS adjusted to {effective_output_fps} for quality fixes.")

    # Watermark removal toggle
    st.sidebar.subheader("Watermark Removal")
    st.session_state.remove_watermark = st.sidebar.toggle(
        "Remove a watermark from the video",
        value=st.session_state.remove_watermark
    )

    st.sidebar.caption(f"Selected size: {text_size}px")
    with st.sidebar.expander("Font Preview", expanded=False):
        st.markdown(render_font_preview_block(font_choice, text_size, font_style), unsafe_allow_html=True)

    # Output enhancement level (4K and above only)
    st.sidebar.subheader("Enhancement Level")
    enhancement_choice = st.sidebar.selectbox(
        "Output Resolution",
        [
            "4K (3840 long edge)",
            "8K (7680 long edge)",
            "12K (11520 long edge)"
        ]
    )

    source_long_edge = max(size[0], size[1])
    estimated_duration = max(duration, minimum_duration_target) if auto_quality_fixes else duration
    size_4k_mb = estimate_output_size_mb(input_file_size_bytes, estimated_duration, source_long_edge, 3840, fps, effective_output_fps)
    size_8k_mb = estimate_output_size_mb(input_file_size_bytes, estimated_duration, source_long_edge, 7680, fps, effective_output_fps)
    size_12k_mb = estimate_output_size_mb(input_file_size_bytes, estimated_duration, source_long_edge, 11520, fps, effective_output_fps)
    st.sidebar.caption("Estimated output storage from uploaded file:")
    st.sidebar.markdown(
        "\n".join([
            f"- 4K: ~{size_4k_mb/1024:.2f} GB ({size_4k_mb:.0f} MB)",
            f"- 8K: ~{size_8k_mb/1024:.2f} GB ({size_8k_mb:.0f} MB)",
            f"- 12K: ~{size_12k_mb/1024:.2f} GB ({size_12k_mb:.0f} MB)"
        ])
    )
    
    # Get first frame for preview
    first_frame = video_clip.get_frame(0)
    effect_type = "Blur"
    default_vals = (50, 80, 20, 10)

    if st.session_state.remove_watermark:
        # Effect selection
        effect_type = st.sidebar.selectbox("Select Removal Effect", ["Blur", "Pixelate"])

        # Area selection parameters
        st.sidebar.subheader("Watermark Removal Area")

        # Auto-detect function
        def auto_detect_watermark(frame):
            """Auto-detect potential watermark areas based on brightness and edges"""
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Look for bright areas (watermarks are often light colored)
            bright_areas = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1]

            # Find contours of bright areas
            contours, _ = cv2.findContours(bright_areas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                # Get the largest contour (likely watermark)
                largest_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest_contour)

                # Convert to percentages
                frame_h, frame_w = frame.shape[:2]
                x_pct = int((x / frame_w) * 100)
                y_pct = int((y / frame_h) * 100)
                w_pct = int((w / frame_w) * 100)
                h_pct = int((h / frame_h) * 100)

                return x_pct, y_pct, w_pct, h_pct
            return None

        if "x_pos" not in st.session_state:
            st.session_state.x_pos = default_vals[0]
        if "y_pos" not in st.session_state:
            st.session_state.y_pos = default_vals[1]
        if "width" not in st.session_state:
            st.session_state.width = default_vals[2]
        if "height" not in st.session_state:
            st.session_state.height = default_vals[3]

        def adjust_value(name, delta, minimum, maximum):
            st.session_state[name] = max(minimum, min(maximum, st.session_state[name] + delta))

        # Try auto-detection
        if st.sidebar.button("🔍 Auto-Detect Watermark"):
            detected = auto_detect_watermark(first_frame)
            if detected:
                default_vals = detected
                st.session_state.x_pos, st.session_state.y_pos, st.session_state.width, st.session_state.height = detected
                st.sidebar.success(f"Detected at: {detected}")
            else:
                st.sidebar.warning("No watermark detected. Adjust manually.")

        col1, col2 = st.sidebar.columns(2)
        with col1:
            st.caption("X Position (%)")
            x_button_col1, x_value_col, x_button_col2 = st.columns([1, 2, 1])
            with x_button_col1:
                st.button("▲", key="x_pos_up", use_container_width=True, on_click=adjust_value, args=("x_pos", 1, 0, 100))
            with x_value_col:
                st.markdown(f"<div style='text-align:center; padding-top:0.35rem; font-weight:600;'>{st.session_state.x_pos}%</div>", unsafe_allow_html=True)
            with x_button_col2:
                st.button("▼", key="x_pos_down", use_container_width=True, on_click=adjust_value, args=("x_pos", -1, 0, 100))

            st.caption("Y Position (%)")
            y_button_col1, y_value_col, y_button_col2 = st.columns([1, 2, 1])
            with y_button_col1:
                st.button("▲", key="y_pos_up", use_container_width=True, on_click=adjust_value, args=("y_pos", 1, 0, 100))
            with y_value_col:
                st.markdown(f"<div style='text-align:center; padding-top:0.35rem; font-weight:600;'>{st.session_state.y_pos}%</div>", unsafe_allow_html=True)
            with y_button_col2:
                st.button("▼", key="y_pos_down", use_container_width=True, on_click=adjust_value, args=("y_pos", -1, 0, 100))
        with col2:
            st.caption("Width (%)")
            w_button_col1, w_value_col, w_button_col2 = st.columns([1, 2, 1])
            with w_button_col1:
                st.button("▲", key="width_up", use_container_width=True, on_click=adjust_value, args=("width", 1, 1, 100))
            with w_value_col:
                st.markdown(f"<div style='text-align:center; padding-top:0.35rem; font-weight:600;'>{st.session_state.width}%</div>", unsafe_allow_html=True)
            with w_button_col2:
                st.button("▼", key="width_down", use_container_width=True, on_click=adjust_value, args=("width", -1, 1, 100))

            st.caption("Height (%)")
            h_button_col1, h_value_col, h_button_col2 = st.columns([1, 2, 1])
            with h_button_col1:
                st.button("▲", key="height_up", use_container_width=True, on_click=adjust_value, args=("height", 1, 1, 100))
            with h_value_col:
                st.markdown(f"<div style='text-align:center; padding-top:0.35rem; font-weight:600;'>{st.session_state.height}%</div>", unsafe_allow_html=True)
            with h_button_col2:
                st.button("▼", key="height_down", use_container_width=True, on_click=adjust_value, args=("height", -1, 1, 100))
    else:
        if "x_pos" not in st.session_state:
            st.session_state.x_pos = default_vals[0]
        if "y_pos" not in st.session_state:
            st.session_state.y_pos = default_vals[1]
        if "width" not in st.session_state:
            st.session_state.width = default_vals[2]
        if "height" not in st.session_state:
            st.session_state.height = default_vals[3]
    
    blur_intensity = st.sidebar.slider("Blur/Pixelate Intensity", 1, 50, 15)
    
    # Calculate pixel coordinates from percentages
    h, w = first_frame.shape[:2]
    x_pos = st.session_state.x_pos
    y_pos = st.session_state.y_pos
    width = st.session_state.width
    height = st.session_state.height

    x_pixel = int(w * x_pos / 100)
    y_pixel = int(h * y_pos / 100)
    width_pixel = int(w * width / 100)
    height_pixel = int(h * height / 100)

    enhancement_long_edge = {
        "4K (3840 long edge)": 3840,
        "8K (7680 long edge)": 7680,
        "12K (11520 long edge)": 11520
    }[enhancement_choice]

    # Preserve aspect ratio while ensuring output is never below the selected level.
    src_w, src_h = size
    src_long = max(src_w, src_h)
    upscale_factor = max(1.0, enhancement_long_edge / src_long)
    target_w = int(round(src_w * upscale_factor))
    target_h = int(round(src_h * upscale_factor))

    # libx264 requires even dimensions.
    if target_w % 2 != 0:
        target_w += 1
    if target_h % 2 != 0:
        target_h += 1

    st.sidebar.caption(f"Enhanced output: {target_w}x{target_h}")
    
    st.session_state.selected_area = {
        'x': x_pixel,
        'y': y_pixel,
        'width': width_pixel,
        'height': height_pixel,
        'effect': effect_type,
        'intensity': blur_intensity,
        'font': font_choice,
        'font_style': font_style,
        'text_size': text_size,
        'opacity': opacity
    }
    
    # Main content area
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Original Video")
        st.video(temp_video_path)

        if st.session_state.remove_watermark:
            # Show original first frame with area selection
            st.subheader("Watermark Removal Area Preview")
            preview_frame = first_frame.copy()
            cv2.rectangle(preview_frame,
                         (x_pixel, y_pixel),
                         (x_pixel + width_pixel, y_pixel + height_pixel),
                         (0, 255, 0), 2)
            st.image(preview_frame, width=700, channels="BGR")

        # Show watermark text preview
        st.subheader("Watermark Text Preview")
        preview_with_text = first_frame.copy()
        frame_rgb = cv2.cvtColor(preview_with_text, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb.astype('uint8'))
        
        txt_overlay = Image.new('RGBA', pil_image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(txt_overlay)

        prev_font = load_font(font_choice, text_size)
        text_width, text_height = get_text_size(draw, watermark_text, prev_font, font_style)
        # Place replacement text over the selected old-watermark area.
        text_x = x_pixel + max((width_pixel - text_width) // 2, 0)
        text_y = y_pixel + max((height_pixel - text_height) // 2, 0)
        text_x = max(0, min(text_x, size[0] - text_width - 1))
        text_y = max(0, min(text_y, size[1] - text_height - 1))
        
        alpha = int(255 * (opacity / 100))
        draw_styled_watermark(txt_overlay, watermark_text, prev_font, text_x, text_y, alpha, font_style)

        if add_custom_text and custom_text.strip():
            custom_font_obj = load_font(custom_font, custom_text_size)
            custom_text_w, custom_text_h = get_text_size(draw, custom_text, custom_font_obj, custom_font_style)
            custom_x, custom_y = compute_text_position(
                size[0],
                size[1],
                custom_text_w,
                custom_text_h,
                custom_position,
                custom_x_pct,
                custom_y_pct,
                24
            )

            if custom_bg_enabled:
                bg_rgb = hex_to_rgb(custom_bg_color)
                bg_alpha = int(255 * (custom_bg_opacity / 100.0))
                rect = [
                    (custom_x - custom_bg_padding, custom_y - custom_bg_padding),
                    (custom_x + custom_text_w + custom_bg_padding, custom_y + custom_text_h + custom_bg_padding)
                ]
                if custom_bg_rounded:
                    draw.rounded_rectangle(rect, radius=10, fill=(bg_rgb[0], bg_rgb[1], bg_rgb[2], bg_alpha))
                else:
                    draw.rectangle(rect, fill=(bg_rgb[0], bg_rgb[1], bg_rgb[2], bg_alpha))

            text_rgb = hex_to_rgb(custom_text_color)
            text_alpha = int(255 * (custom_text_opacity / 100.0))
            draw_styled_text(
                txt_overlay,
                custom_text,
                custom_font_obj,
                custom_x,
                custom_y,
                (text_rgb[0], text_rgb[1], text_rgb[2], text_alpha),
                custom_font_style,
                shadow_enabled=custom_shadow
            )
        
        pil_image = pil_image.convert('RGBA')
        pil_image = Image.alpha_composite(pil_image, txt_overlay)
        pil_image = pil_image.convert('RGB')
        
        preview_with_text = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        st.image(preview_with_text, width=700, channels="BGR")
    
    with col2:
        st.subheader("Enhanced Video")

        # Auto quality report from current settings and input metadata.
        quality_items = [
            {
                "label": "Dynamic Content",
                "ok": auto_quality_fixes and dynamic_motion,
                "detail": "Enable Auto quality fixes + Keep video dynamic to add subtle motion and reduce static-looking output."
            },
            {
                "label": "Resolution / FPS",
                "ok": enhancement_long_edge >= 3840 and effective_output_fps >= 30,
                "detail": f"Current: {enhancement_choice}, {effective_output_fps} FPS"
            },
            {
                "label": "Original Edits",
                "ok": auto_quality_fixes and (add_creative_intro or narration_file is not None),
                "detail": "Use creative intro and/or upload narration audio for stronger originality signals."
            },
            {
                "label": "Minimum Length",
                "ok": max(duration, minimum_duration_target if auto_quality_fixes else duration) >= 8,
                "detail": f"Input: {duration:.2f}s, Target minimum: {minimum_duration_target if auto_quality_fixes else int(duration)}s"
            }
        ]
        quality_pass_count = sum(1 for item in quality_items if item["ok"])

        with st.expander("Auto Quality Report", expanded=True):
            st.metric("Quality Fix Score", f"{quality_pass_count}/{len(quality_items)}")
            for item in quality_items:
                if item["ok"]:
                    st.success(f"{item['label']}: PASS | {item['detail']}")
                else:
                    st.warning(f"{item['label']}: NEEDS IMPROVEMENT | {item['detail']}")
        
        # Process button
        if st.button("🚀 Process Video", key="process_btn"):
            progress_bar = st.progress(0, text="Preparing processing...")
            status_box = st.empty()
            with st.spinner("Processing video... This may take a few minutes"):
                try:
                    progress_bar.progress(5, text="Preparing frame processing...")
                    status_box.write("Preparing frame processing...")

                    narration_temp_path = None
                    narration_clip = None

                    if narration_file is not None:
                        narration_suffix = Path(narration_file.name).suffix or ".mp3"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=narration_suffix) as narration_tmp:
                            narration_tmp.write(narration_file.getvalue())
                            narration_temp_path = narration_tmp.name

                    # Create output video with effects
                    def process_frame(frame, t=0.0):
                        """Apply watermark removal effect and text overlay to frame"""
                        # Ensure frame is writable (convert if read-only)
                        frame = np.array(frame, copy=True)

                        if auto_quality_fixes and dynamic_motion:
                            # Add subtle camera-like movement to avoid static-looking output.
                            dx = int(3 * np.sin((2 * np.pi / 5.0) * t))
                            dy = int(2 * np.cos((2 * np.pi / 7.0) * t))
                            transform = np.float32([[1, 0, dx], [0, 1, dy]])
                            frame = cv2.warpAffine(
                                frame,
                                transform,
                                (frame.shape[1], frame.shape[0]),
                                flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_REFLECT
                            )
                        
                        x = st.session_state.selected_area['x']
                        y = st.session_state.selected_area['y']
                        w = st.session_state.selected_area['width']
                        h = st.session_state.selected_area['height']
                        intensity = st.session_state.selected_area['intensity']
                        effect = st.session_state.selected_area['effect']

                        if st.session_state.remove_watermark and w > 0 and h > 0:
                            # Extract the region
                            roi = frame[y:y+h, x:x+w].copy()

                            if effect == "Blur":
                                # Apply blur
                                kernel_size = (intensity * 2 + 1, intensity * 2 + 1)
                                roi = cv2.GaussianBlur(roi, kernel_size, 0)
                            else:  # Pixelate
                                # Apply pixelation
                                temp = cv2.resize(roi, (intensity, intensity), interpolation=cv2.INTER_LINEAR)
                                roi = cv2.resize(temp, (w, h), interpolation=cv2.INTER_NEAREST)

                            # Apply the processed region back
                            frame[y:y+h, x:x+w] = roi
                        
                        # Add watermark text using PIL with transparency
                        # Convert BGR to RGB for PIL
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        pil_image = Image.fromarray(frame_rgb.astype('uint8'))
                        
                        # Create transparent overlay for text
                        txt_overlay = Image.new('RGBA', pil_image.size, (0, 0, 0, 0))
                        draw = ImageDraw.Draw(txt_overlay)
                        
                        # Select font
                        font_name = st.session_state.selected_area.get('font', 'Arial')
                        font_style = st.session_state.selected_area.get('font_style', 'Regular')
                        font_size = st.session_state.selected_area.get('text_size', 16)

                        font = load_font(font_name, font_size)
                        
                        # Get text bounding box for positioning
                        text_width, text_height = get_text_size(draw, watermark_text, font, font_style)

                        # Place replacement text over the old watermark area.
                        text_x = x + max((w - text_width) // 2, 0)
                        text_y = y + max((h - text_height) // 2, 0)
                        text_x = max(0, min(text_x, size[0] - text_width - 1))
                        text_y = max(0, min(text_y, size[1] - text_height - 1))
                        
                        # Calculate alpha value from opacity percentage
                        opacity_pct = st.session_state.selected_area.get('opacity', 80)
                        alpha = int(255 * (opacity_pct / 100))

                        draw_styled_watermark(txt_overlay, watermark_text, font, text_x, text_y, alpha, font_style)

                        if add_custom_text and custom_text.strip():
                            custom_font_obj = load_font(custom_font, custom_text_size)
                            custom_text_w, custom_text_h = get_text_size(draw, custom_text, custom_font_obj, custom_font_style)
                            custom_x, custom_y = compute_text_position(
                                size[0],
                                size[1],
                                custom_text_w,
                                custom_text_h,
                                custom_position,
                                custom_x_pct,
                                custom_y_pct,
                                24
                            )

                            if custom_bg_enabled:
                                bg_rgb = hex_to_rgb(custom_bg_color)
                                bg_alpha = int(255 * (custom_bg_opacity / 100.0))
                                rect = [
                                    (custom_x - custom_bg_padding, custom_y - custom_bg_padding),
                                    (custom_x + custom_text_w + custom_bg_padding, custom_y + custom_text_h + custom_bg_padding)
                                ]
                                if custom_bg_rounded:
                                    draw.rounded_rectangle(rect, radius=10, fill=(bg_rgb[0], bg_rgb[1], bg_rgb[2], bg_alpha))
                                else:
                                    draw.rectangle(rect, fill=(bg_rgb[0], bg_rgb[1], bg_rgb[2], bg_alpha))

                            text_rgb = hex_to_rgb(custom_text_color)
                            text_alpha = int(255 * (custom_text_opacity / 100.0))
                            draw_styled_text(
                                txt_overlay,
                                custom_text,
                                custom_font_obj,
                                custom_x,
                                custom_y,
                                (text_rgb[0], text_rgb[1], text_rgb[2], text_alpha),
                                custom_font_style,
                                shadow_enabled=custom_shadow
                            )

                        if auto_quality_fixes and add_creative_intro and t < 2.5:
                            intro_draw = ImageDraw.Draw(txt_overlay)
                            intro_font = load_font("Arial", max(16, int(font_size * 0.9)))
                            intro_text = "Original Edit"
                            intro_draw.rectangle([(18, 18), (240, 68)], fill=(10, 10, 10, 180))
                            intro_draw.text((28, 30), intro_text, fill=(255, 255, 255, 235), font=intro_font)
                        
                        # Convert overlay to RGB and blend with original frame
                        pil_image = pil_image.convert('RGBA')
                        pil_image = Image.alpha_composite(pil_image, txt_overlay)
                        pil_image = pil_image.convert('RGB')
                        
                        # Convert back to BGR
                        frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                        return frame
                    
                    # Process video at source resolution first.
                    progress_bar.progress(20, text="Applying watermark removal and text overlay...")
                    status_box.write("Applying watermark removal and text overlay...")
                    processed_clip = video_clip.fl(lambda gf, t: process_frame(gf(t), t))

                    if auto_quality_fixes and narration_temp_path is not None:
                        narration_clip = AudioFileClip(narration_temp_path)
                        usable_duration = min(processed_clip.duration, narration_clip.duration)
                        narration_clip = narration_clip.subclip(0, usable_duration)
                        if processed_clip.audio is not None:
                            mixed_audio = CompositeAudioClip([
                                processed_clip.audio.volumex(0.65),
                                narration_clip.volumex(1.0)
                            ]).set_duration(processed_clip.duration)
                            processed_clip = processed_clip.set_audio(mixed_audio)
                        else:
                            processed_clip = processed_clip.set_audio(narration_clip.set_duration(processed_clip.duration))

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as processed_tmp:
                        processed_path = processed_tmp.name

                    progress_bar.progress(40, text="Encoding processed video...")
                    status_box.write("Encoding processed video...")
                    processed_clip.write_videofile(
                        processed_path,
                        codec='libx264',
                        audio_codec='aac',
                        preset=render_profile["moviepy_preset"],
                        threads=os.cpu_count() or 4,
                        fps=effective_output_fps,
                        verbose=False,
                        logger=None,
                    )

                    src_w_clip, src_h_clip = processed_clip.size
                    required_pad_seconds = max(0.0, minimum_duration_target - duration) if auto_quality_fixes else 0.0
                    needs_scale = (src_w_clip, src_h_clip) != (target_w, target_h)
                    needs_pad = required_pad_seconds > 0.01

                    if needs_scale or needs_pad:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as output_file:
                            output_path = output_file.name

                        if needs_scale and needs_pad:
                            progress_bar.progress(70, text=f"Upscaling and extending duration to {minimum_duration_target}s...")
                            status_box.write(f"Upscaling and extending duration to {minimum_duration_target}s...")
                        elif needs_scale:
                            progress_bar.progress(70, text=f"Upscaling to {target_w}x{target_h} with FFmpeg...")
                            status_box.write(f"Upscaling to {target_w}x{target_h} with FFmpeg...")
                        else:
                            progress_bar.progress(70, text=f"Extending duration to {minimum_duration_target}s...")
                            status_box.write(f"Extending duration to {minimum_duration_target}s...")

                        vf_filters = []
                        if needs_scale:
                            vf_filters.append(f"scale={target_w}:{target_h}:flags=lanczos")
                        if needs_pad:
                            vf_filters.append(f"tpad=stop_mode=clone:stop_duration={required_pad_seconds:.3f}")

                        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                        ffmpeg_cmd = [
                            ffmpeg_exe,
                            "-y",
                            "-i", processed_path,
                            "-vf", ",".join(vf_filters),
                            "-r", str(effective_output_fps),
                            "-c:v", "libx264",
                            "-preset", render_profile["ffmpeg_preset"],
                            "-crf", render_profile["crf"],
                            "-threads", str(os.cpu_count() or 4),
                            "-c:a", "aac",
                            output_path
                        ]
                        ffmpeg_result = subprocess.run(
                            ffmpeg_cmd,
                            capture_output=True,
                            text=True
                        )
                        if ffmpeg_result.returncode != 0:
                            raise RuntimeError(ffmpeg_result.stderr.strip() or "FFmpeg upscale failed.")
                    else:
                        output_path = processed_path

                    progress_bar.progress(90, text="Finalizing output...")
                    status_box.write("Finalizing output...")

                    final_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                    final_size_text = f"{final_size_mb / 1024:.2f} GB" if final_size_mb >= 1024 else f"{final_size_mb:.1f} MB"
                    
                    # Display enhanced video
                    st.video(output_path)
                    
                    # Download button
                    download_col, storage_col = st.columns([2, 1])
                    with download_col:
                        with open(output_path, 'rb') as f:
                            st.download_button(
                                label="⬇️ Download Enhanced Video",
                                data=f,
                                file_name="enhanced_video.mp4",
                                mime="video/mp4"
                            )
                    with storage_col:
                        st.metric("Enhanced Storage", final_size_text)
                    
                    progress_bar.progress(100, text="Processing complete")
                    status_box.success("Processing complete")
                    st.success("✅ Video processing complete!")
                    
                    # Cleanup
                    if narration_clip is not None:
                        narration_clip.close()
                    processed_clip.close()
                    if narration_temp_path is not None and os.path.exists(narration_temp_path):
                        os.remove(narration_temp_path)
                    
                except Exception as e:
                    st.error(f"❌ Error processing video: {str(e)}")
                    st.info("Make sure you have all required dependencies installed:\npip install streamlit moviepy opencv-python pillow")
    
    # Cleanup
    video_clip.close()

else:
    st.info("👈 Upload an MP4 video to get started")
    
    # Display instructions
    with st.expander("📖 How to use"):
        st.markdown("""
        1. **Upload Video**: Click the upload button in the sidebar
        2. **Configure Settings**:
           - Enter custom watermark text
           - Select blur or pixelate effect
           - Adjust the area position and size (as percentages)
           - Set the effect intensity
        3. **Preview**: See the selected area highlighted in green on the original frame
        4. **Process**: Click the "Process Video" button
        5. **Download**: After processing, download your enhanced video
        
        **Features**:
        - Remove watermarks with blur or pixelation effects
        - Add custom text watermark to bottom-right corner
        - Side-by-side preview of original and enhanced videos
        - Adjustable effect intensity
        - Download processed video
        """)

# Add footer
st.markdown("---")
st.markdown("🎨 Video Enhancement Tool | Powered by Streamlit & MoviePy")
