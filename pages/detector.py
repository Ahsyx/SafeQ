import streamlit as st
import sys, os, json, time, io
import numpy as np
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import inject_hazard, HAZARD_REGISTRY
from streamlit_js_eval import get_geolocation

st.set_page_config(page_title="SafeQ Detector", layout="wide", page_icon="📷")

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #00ff88; color: black; font-weight: bold; }
    .result-box { background-color: #1e2130; padding: 16px; border-radius: 10px; border: 1px solid #333; color: white; margin-bottom: 10px; }
    .found   { border-left: 5px solid #ff4b4b; }
    .clear   { border-left: 5px solid #00ff88; }
    .debug   { border-left: 5px solid #888; font-size: 0.85rem; }
    .msg-box { background-color: #1a2a1a; border: 1px solid #00ff88; border-radius: 8px;
               padding: 12px; margin-bottom: 8px; color: white; font-size: 0.9rem; }
    </style>
""", unsafe_allow_html=True)

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DETECTIONS_FILE = os.path.join(BASE_DIR, "detections.json")
ALERTS_FILE     = os.path.join(BASE_DIR, "alerts.json")

# ── Model ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def load_model():
    from ultralytics import YOLO
    for name in ["safeq_best_model.pt", "best.pt"]:
        full = os.path.join(BASE_DIR, name)
        if os.path.exists(full):
            return YOLO(full), name
    return YOLO("yolov8s.pt"), "yolov8s.pt (pretrained fallback)"

model, model_name = load_model()

# ── Alert helpers ──────────────────────────────────────────────────────────────
def load_alerts():
    if not os.path.exists(ALERTS_FILE):
        return []
    try:
        with open(ALERTS_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def save_alert(sender, message, lat, lon):
    alerts = load_alerts()
    alerts.append({
        "time":    time.strftime("%Y-%m-%d %H:%M:%S"),
        "sender":  sender,
        "message": message,
        "lat":     lat,
        "lon":     lon
    })
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f, indent=2)

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("📷 SafeQ Road Hazard Detector")
st.caption(f"Model: `{model_name}` | Standalone — no login required")

with st.expander("🔧 Model Debug Info", expanded=False):
    st.write(f"**Classes:** {model.names}")
    st.info("If you see `person, car...` place `safeq_best_model.pt` in project root.")

st.divider()

# ── GPS ───────────────────────────────────────────────────────────────────────
gps_lat, gps_lon = 9.9816, 76.2999  # default Kochi

location = get_geolocation()
if location and "coords" in location:
    gps_lat = location["coords"]["latitude"]
    gps_lon = location["coords"]["longitude"]
    gps_acc = round(location["coords"]["accuracy"])
    st.success(f"📍 GPS locked: **{gps_lat:.6f}, {gps_lon:.6f}** (±{gps_acc}m)")
else:
    col_gps, col_msg = st.columns([1, 3])
    with col_gps:
        if st.button("📡 Get My Location", key="gps_btn"):
            st.rerun()  # triggers get_geolocation on next load
    with col_msg:
        st.caption("⚠️ GPS not detected — enter location manually or click to retry")

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_detect, tab_report, tab_alerts = st.tabs(["🔍 Detect Hazard", "📢 Send Alert", "🔔 Community Alerts"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — HAZARD DETECTOR
# ══════════════════════════════════════════════════════════════════════════════
with tab_detect:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("1️⃣ Upload Road Image")
        uploaded = st.file_uploader("Drop a road photo here", type=["jpg", "jpeg", "png", "bmp"])
        conf = st.slider("Confidence Threshold", 0.01, 0.90, 0.10, 0.01,
                         help="Lower = more detections. Try 0.05 if nothing shows.")

    with col2:
        st.subheader("2️⃣ Location")
        lat = st.number_input("Latitude",  value=gps_lat, format="%.6f", step=0.0001, key="det_lat")
        lon = st.number_input("Longitude", value=gps_lon, format="%.6f", step=0.0001, key="det_lon")
        st.caption("📍 Quick presets:")
        p1, p2, p3 = st.columns(3)
        if p1.button("Tripunithura", key="det_trip"): lat, lon = 9.9449, 76.3356
        if p2.button("Kakanad",      key="det_kak"):  lat, lon = 10.0159, 76.3419
        if p3.button("Edapally",     key="det_edp"):  lat, lon = 10.0261, 76.3083
        st.divider()
        reporter_id = st.text_input("Reporter ID (optional)", placeholder="e.g. KL-07-AW-1234")

    if uploaded:
        try:
            img = Image.open(io.BytesIO(uploaded.read())).convert("RGB")
        except Exception as e:
            st.error(f"❌ Could not open image: {e}")
            st.stop()

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
                {"hazard": CLASS_TO_HAZARD[c.lower()], "class": c, "confidence": round(cv, 3)}
                for c, cv in all_boxes if c.lower() in CLASS_TO_HAZARD
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
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "lat": lat, "lon": lon,
                    "reporter": reporter_id or "Anonymous",
                    "detections": detections,
                    "processed": False
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

                # Auto community alert
                hazard_names = ", ".join(set(d['hazard'] for d in detections))
                save_alert(
                    sender=reporter_id or "SafeQ Scanner",
                    message=f"⚠️ Auto-detected: {hazard_names} at ({lat:.4f}, {lon:.4f}). Avoid this road!",
                    lat=lat, lon=lon
                )
                st.success(f"📡 Hazard reported & community alerted at ({lat:.4f}, {lon:.4f})")
            else:
                if all_boxes:
                    found = list(set(c for c, _ in all_boxes))
                    st.markdown(f"""
                        <div class="result-box debug">
                            ℹ️ Detected: <b>{', '.join(found)}</b> — not in hazard registry.
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                        <div class="result-box clear">
                            ✅ <b>No hazards detected</b> — road looks clear.
                        </div>
                    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — PERSON TO PERSON MANUAL ALERT
# ══════════════════════════════════════════════════════════════════════════════
with tab_report:
    st.subheader("📢 Send a Road Alert to the Community")
    st.caption("Warn other SafeQ users about hazards you spot — no image needed.")

    r_col1, r_col2 = st.columns([2, 1])

    with r_col1:
        sender_name = st.text_input("Your Name / Vehicle ID", placeholder="e.g. Ashik / KL-07-CC-0007")
        message     = st.text_area(
            "Alert Message",
            placeholder="e.g. Major accident near Vyttila flyover, avoid NH66. Water logging on Palarivattom junction.",
            height=120
        )
        hazard_tag = st.selectbox("Hazard Type", list(HAZARD_REGISTRY.keys()), key="alert_hazard")

    with r_col2:
        st.caption("📍 Alert Location")
        alert_lat = st.number_input("Latitude",  value=gps_lat, format="%.6f", step=0.0001, key="alert_lat")
        alert_lon = st.number_input("Longitude", value=gps_lon, format="%.6f", step=0.0001, key="alert_lon")
        st.caption("Quick presets:")
        a1, a2, a3 = st.columns(3)
        if a1.button("Vyttila",  key="alt_vyt"): alert_lat, alert_lon = 9.9667, 76.3083
        if a2.button("Edapally", key="alt_edp"): alert_lat, alert_lon = 10.0261, 76.3083
        if a3.button("Kakkanad", key="alt_kak"): alert_lat, alert_lon = 10.0159, 76.3419

    if st.button("📡 Broadcast Alert", use_container_width=True):
        if sender_name and message:
            save_alert(sender=sender_name, message=message, lat=alert_lat, lon=alert_lon)
            # Inject into detections.json so map picks it up
            record = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "lat": alert_lat, "lon": alert_lon,
                "reporter": sender_name,
                "detections": [{"hazard": hazard_tag, "class": "manual report", "confidence": 1.0}],
                "processed": False
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

            st.success("✅ Alert broadcast to all SafeQ users! Map updates within 5 seconds.")
            st.balloons()
        else:
            st.warning("Please enter your name and a message.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — COMMUNITY ALERTS FEED
# ══════════════════════════════════════════════════════════════════════════════
with tab_alerts:
    st.subheader("🔔 Live Community Alerts")
    st.caption("Real-time hazard reports from SafeQ users on the road.")

    alerts = load_alerts()
    if alerts:
        for alert in reversed(alerts[-20:]):
            st.markdown(f"""
                <div class="msg-box">
                    🕐 <b>{alert['time']}</b> &nbsp;|&nbsp; 👤 <b>{alert['sender']}</b><br>
                    💬 {alert['message']}<br>
                    <span style="color:#aaa;font-size:0.8rem;">
                        📍 ({alert['lat']:.4f}, {alert['lon']:.4f})
                    </span>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No alerts yet — be the first to report a hazard!")

    if st.button("🔄 Refresh Alerts"):
        st.rerun()

# ── Detection Queue (collapsed) ────────────────────────────────────────────────
st.divider()
with st.expander("📋 Detection Queue", expanded=False):
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