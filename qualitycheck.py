import tempfile
from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from moviepy.editor import VideoFileClip


st.set_page_config(page_title="Video Quality Check", layout="wide")
st.title("Video Quality Check")
st.markdown("Analyze a video for recommendation-readiness signals and get actionable fixes.")


MIN_DURATION_SEC = 8
MIN_WIDTH = 1080
MIN_HEIGHT = 1920
MIN_FPS = 24


def save_uploaded_file(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix or ".mp4") as tmp:
        tmp.write(uploaded_file.getvalue())
        return tmp.name


def sample_frame_indices(frame_count, max_samples=180):
    if frame_count <= 0:
        return []
    samples = min(frame_count, max_samples)
    return np.linspace(0, frame_count - 1, samples, dtype=int).tolist()


def analyze_static_content(video_path):
    cap = cv2.VideoCapture(video_path)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = sample_frame_indices(frame_count)

    prev_gray = None
    diffs = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            diffs.append(float(np.mean(diff)))
        prev_gray = gray

    cap.release()

    if not diffs:
        return {
            "motion_score": 0.0,
            "is_mostly_static": False,
            "note": "Could not sample enough frames for motion analysis."
        }

    motion_score = float(np.mean(diffs))
    is_mostly_static = motion_score < 2.0
    return {
        "motion_score": motion_score,
        "is_mostly_static": is_mostly_static,
        "note": "Lower score means more static content."
    }


def analyze_video(video_path):
    with VideoFileClip(video_path) as clip:
        duration = float(clip.duration or 0)
        fps = float(clip.fps or 0)
        width, height = clip.size

    static_info = analyze_static_content(video_path)

    checks = []

    checks.append({
        "name": "Duration",
        "ok": duration >= MIN_DURATION_SEC,
        "detail": f"{duration:.2f}s (target: >= {MIN_DURATION_SEC}s)"
    })

    checks.append({
        "name": "Resolution",
        "ok": (width >= MIN_WIDTH and height >= MIN_HEIGHT) or (height >= MIN_WIDTH and width >= MIN_HEIGHT),
        "detail": f"{width}x{height} (recommended vertical: {MIN_WIDTH}x{MIN_HEIGHT} or higher)"
    })

    checks.append({
        "name": "Frame Rate",
        "ok": fps >= MIN_FPS,
        "detail": f"{fps:.2f} FPS (target: >= {MIN_FPS})"
    })

    checks.append({
        "name": "Motion / Dynamic Content",
        "ok": not static_info["is_mostly_static"],
        "detail": f"Motion score: {static_info['motion_score']:.2f} ({static_info['note']})"
    })

    passed = sum(1 for c in checks if c["ok"])
    total = len(checks)

    return {
        "duration": duration,
        "fps": fps,
        "width": width,
        "height": height,
        "checks": checks,
        "score": int((passed / total) * 100) if total else 0,
        "passed": passed,
        "total": total,
    }


def render_result_card(label, ok, detail):
    if ok:
        st.success(f"{label}: PASS\n\n{detail}")
    else:
        st.warning(f"{label}: NEEDS IMPROVEMENT\n\n{detail}")


uploaded = st.file_uploader("Upload video (MP4)", type=["mp4"])

if uploaded:
    video_path = save_uploaded_file(uploaded)

    st.video(video_path)

    if st.button("Run Quality Check", type="primary"):
        with st.spinner("Analyzing video..."):
            report = analyze_video(video_path)

        left, right = st.columns([1, 1])
        with left:
            st.metric("Quality Score", f"{report['score']}%")
            st.metric("Passed Checks", f"{report['passed']}/{report['total']}")

        with right:
            st.write("Video Stats")
            st.write(f"- Duration: {report['duration']:.2f}s")
            st.write(f"- FPS: {report['fps']:.2f}")
            st.write(f"- Resolution: {report['width']}x{report['height']}")

        st.subheader("Automated Checks")
        for item in report["checks"]:
            render_result_card(item["name"], item["ok"], item["detail"])

        st.subheader("Originality Checklist (Manual)")
        voiceover = st.checkbox("I added my own voiceover/commentary")
        recut = st.checkbox("I made meaningful edits (timing, transitions, structure)")
        rights = st.checkbox("I have rights/permission for all source footage")
        no_repost = st.checkbox("This is not just a direct repost from another source")

        manual_pass = sum([voiceover, recut, rights, no_repost])
        st.info(f"Manual originality checks passed: {manual_pass}/4")

        if report["score"] >= 75 and manual_pass >= 3:
            st.success("This video looks recommendation-ready based on current checks.")
        else:
            st.warning("Improve flagged areas before publishing for better recommendation potential.")

        st.subheader("Suggested Fixes")
        st.write("1. Keep the video dynamic: avoid static frames for long periods.")
        st.write("2. Increase resolution/FPS where possible (vertical format recommended for short-form).")
        st.write("3. Add original narration or edits to avoid low-originality signals.")
        st.write("4. Keep enough length to deliver value, not only a very short clip.")
else:
    st.info("Upload an MP4 file to begin quality analysis.")
