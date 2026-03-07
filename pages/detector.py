import streamlit as st
import sys, os, json, time, io
import numpy as np
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import inject_hazard, HAZARD_REGISTRY

st.set_page_config(page_title="SafeQ Detector", layout="wide", page_icon="📷")

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #00ff88; color: black; font-weight: bold; }
    .result-box { background-color: #1e2130; padding: 16px; border-radius: 10px; border: 1px solid #333; color: white; margin-bottom: 10px; }
    .found { border-left: 5px solid #ff4b4b; }
    .clear { border-left: 5px solid #00ff88; }
    .debug { border-left: 5px solid #888; font-size: 0.85rem; }
    .gps-box { background:#1e2130; border-radius:8px; padding:12px;
               border:1px solid #333; color:white; font-size:0.9rem; }
    </style>
""", unsafe_allow_html=True)

DETECTIONS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "detections.json"
)

@st.cache_resource
def load_model():
    from ultralytics import YOLO
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ["safeq_best_model.pt", "best.pt"]:
        full = os.path.join(base, name)
        if os.path.exists(full):
            return YOLO(full), name
    return YOLO("yolov8s.pt"), "yolov8s.pt (pretrained fallback)"

model, model_name = load_model()

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📷 SafeQ Road Hazard Detector")
st.caption(f"Model: `{model_name}` | Standalone — no login required")

with st.expander("🔧 Model Debug Info", expanded=False):
    st.write(f"**Classes:** {model.names}")
    st.info("If you see `person, car...` the custom model wasn't found. Place `safeq_best_model.pt` in the project root.")

st.divider()

# ── AUTO GPS — fires immediately on page load, no button needed ───────────────
st.components.v1.html("""
    <script>
    (function autoGPS() {
        const status = document.getElementById('gps-status');
        if (!navigator.geolocation) {
            status.innerHTML = '❌ GPS not supported by this browser.';
            return;
        }
        status.innerHTML = '🔄 Fetching location...';
        navigator.geolocation.getCurrentPosition(
            function(pos) {
                const lat = pos.coords.latitude.toFixed(6);
                const lon = pos.coords.longitude.toFixed(6);
                const acc = Math.round(pos.coords.accuracy);
                status.innerHTML = '✅ <b>' + lat + ', ' + lon + '</b> (±' + acc + 'm)';
                const url = new URL(window.parent.location);
                url.searchParams.set('gps_lat', lat);
                url.searchParams.set('gps_lon', lon);
                window.parent.history.replaceState({}, '', url);
            },
            function(err) {
                status.innerHTML = '⚠️ ' + err.message + ' — using manual input below.';
            },
            { enableHighAccuracy: true, timeout: 10000 }
        );
    })();
    </script>
    <div class="gps-box" id="gps-status"
         style="background:#1e2130;border-radius:8px;padding:12px;
                border:1px solid #333;color:white;font-size:0.9rem;">
        🔄 Requesting GPS...
    </div>
""", height=55)

# Read from query params (set by JS above)
params  = st.query_params
gps_lat = float(params.get("gps_lat", 9.9816))
gps_lon = float(params.get("gps_lon", 76.2999))

# ── Main layout ───────────────────────────────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("1️⃣ Upload Road Image")
    uploaded = st.file_uploader("Drop a road photo here", type=["jpg", "jpeg", "png", "bmp"])
    conf = st.slider("Confidence Threshold", 0.01, 0.90, 0.10, 0.01,
                     help="Lower = more detections. Try 0.05 if nothing shows.")

with col2:
    st.subheader("2️⃣ Location")

    if "gps_lat" in params:
        st.success(f"📍 GPS locked: ({gps_lat:.4f}, {gps_lon:.4f})")
    else:
        st.caption("⚠️ GPS pending — using manual input")

    lat = st.number_input("Latitude",  value=gps_lat, format="%.6f", step=0.0001)
    lon = st.number_input("Longitude", value=gps_lon, format="%.6f", step=0.0001)

    st.caption("📍 Quick presets:")
    p1, p2, p3 = st.columns(3)
    if p1.button("Tripunithura"): lat, lon = 9.9449, 76.3356
    if p2.button("Kakanad"):      lat, lon = 10.0159, 76.3419
    if p3.button("Edapally"):     lat, lon = 10.0261, 76.3083

    st.divider()
    reporter_id = st.text_input("Reporter ID (optional)", placeholder="e.g. KL-07-AW-1234")

# ── Detection ─────────────────────────────────────────────────────────────────
if uploaded:
    try:
        img = Image.open(io.BytesIO(uploaded.read())).convert("RGB")
    except Exception as e:
        st.error(f"❌ Could not open image: {e}")
        st.stop()

    # Show small thumbnail only — 300px wide max
    thumb = img.copy()
    thumb.thumbnail((300, 300))

    c_thumb, c_info = st.columns([1, 2])
    with c_thumb:
        st.image(thumb, caption="Preview")
    with c_info:
        st.markdown(f"""
            <div class="result-box debug">
                📐 <b>Size:</b> {img.size[0]}×{img.size[1]}px<br>
                🎯 <b>Conf:</b> {conf}<br>
                🤖 <b>Model:</b> {model_name}<br>
                📍 <b>Location:</b> ({lat:.4f}, {lon:.4f})
            </div>
        """, unsafe_allow_html=True)

    if st.button("🔍 Detect & Report Hazard", use_container_width=True):
        with st.spinner("Running YOLOv8 inference..."):
            results   = model.predict(np.array(img), conf=conf, verbose=False)
            result    = results[0]
            annotated = result.plot()

            all_boxes = [
                (model.names[int(b.cls[0])], float(b.conf[0]))
                for b in result.boxes
            ]

        # Show annotated result at fixed width
        st.image(annotated, caption="Detection Result", width=600)

        with st.expander(f"🔍 Raw detections ({len(all_boxes)} at conf≥{conf})", expanded=True):
            if all_boxes:
                for cls_name, raw_conf in all_boxes:
                    st.write(f"• `{cls_name}` — **{raw_conf:.1%}**")
            else:
                st.warning("No detections. Try lowering confidence to 0.01.")

        CLASS_TO_HAZARD = {
            "pothole":            "Pothole Cluster",
            "crocodile crack":    "Pothole Cluster",
            "longitudinal crack": "Pothole Cluster",
        }

        detections = [
            {"hazard": CLASS_TO_HAZARD[c.lower()], "class": c, "confidence": round(conf_v, 3)}
            for c, conf_v in all_boxes
            if c.lower() in CLASS_TO_HAZARD
        ]

        st.divider()

        if detections:
            st.subheader(f"⚠️ {len(detections)} Hazard(s) Detected")
            for d in detections:
                st.markdown(f"""
                    <div class="result-box found">
                        🔴 <b>{d['class'].title()}</b> &nbsp;|&nbsp;
                        Type: <b>{d['hazard']}</b> &nbsp;|&nbsp;
                        Confidence: <b>{d['confidence']:.0%}</b>
                    </div>
                """, unsafe_allow_html=True)

            record = {
                "time":       time.strftime("%Y-%m-%d %H:%M:%S"),
                "lat":        lat,
                "lon":        lon,
                "reporter":   reporter_id or "Anonymous",
                "detections": detections,
                "processed":  False
            }
            existing = []
            if os.path.exists(DETECTIONS_FILE):
                try:
                    with open(DETECTIONS_FILE) as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            existing.append(record)
            with open(DETECTIONS_FILE, "w") as f:
                json.dump(existing, f, indent=2)

            st.success(f"📡 Hazard reported at ({lat:.4f}, {lon:.4f}) — open main dashboard to see route update.")

        else:
            if all_boxes:
                found = list(set(c for c, _ in all_boxes))
                st.markdown(f"""
                    <div class="result-box debug">
                        ℹ️ Detected: <b>{', '.join(found)}</b> — not in hazard registry.<br>
                        Make sure <code>safeq_best_model.pt</code> is in the project root.
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div class="result-box clear">
                        ✅ <b>No hazards detected</b> — road looks clear.
                    </div>
                """, unsafe_allow_html=True)

# ── Detection Queue ────────────────────────────────────────────────────────────
st.divider()
st.subheader("📋 Detection Queue")
if os.path.exists(DETECTIONS_FILE):
    try:
        with open(DETECTIONS_FILE) as f:
            all_records = json.load(f)
        pending   = [r for r in all_records if not r.get("processed")]
        processed = [r for r in all_records if r.get("processed")]
        ca, cb = st.columns(2)
        ca.metric("Pending", len(pending))
        cb.metric("Injected to map", len(processed))
        for r in reversed(pending[-5:]):
            names = ", ".join(set(d['hazard'] for d in r['detections']))
            st.markdown(f"""
                <div class="result-box found">
                    🕐 {r['time']} &nbsp;|&nbsp; ⚠️ {names} &nbsp;|&nbsp;
                    📍 ({r['lat']:.4f}, {r['lon']:.4f}) &nbsp;|&nbsp; 🚗 {r['reporter']}
                </div>
            """, unsafe_allow_html=True)
    except Exception:
        st.info("No detections yet.")
else:
    st.info("No detections yet — scan an image above.")