# 🛡️ SafeQ: Quantum-Optimized Safety Routing

An autonomous safety dashboard that reimagines GPS routing by prioritizing road quality and patient safety over pure distance. Built for the unique road conditions of Kerala, SafeQ uses a physics-inspired Hamiltonian engine to navigate around hazards in a high-fidelity Digital Twin.

---

### ✨ Technologies

| Category | Tools |
| :--- | :--- |
| **Core Logic** | Python 3.10, NetworkX, NumPy |
| **Digital Twin** | OSMnx (OpenStreetMap Graph Theory) |
| **Perception** | YOLOv8 (Real-time Computer Vision) |
| **Dashboard** | Streamlit, Folium (Geospatial Mapping) |

---

### 🚀 Key Features

* **Hamiltonian Routing Engine** – Treats road hazards (potholes, accidents) as high-energy barriers. The system solves for the **Ground State** path—the one with the absolute lowest risk exposure.
* **Vehicle-Specific Sensitivity** – Dynamic rerouting that adapts to the profile. An **Ambulance (Patient Onboard)** has a sensitivity of **4.0**, making it **20x more sensitive** to road jolts than a heavy truck (0.2).
* **Real-time Hazard Injection** – Automatically "nukes" road segments in the digital twin when the YOLOv8 scanner identifies a threat.
* **Digital Twin Filtering** – Implements an advanced highway-type filter to ensure the AI stays on valid vehicular roads and never takes "desperate" shortcuts through residential backyards.
* **Dual-Path Comparison** – Real-time visual contrast between the standard "blind" shortest path (**Red Dashed**) and the SafeQ optimized route (**Green Solid**).

---

### 📍 The Process

The goal was to solve the "last mile" safety problem for emergency vehicles in Kochi. Standard A* or Dijkstra algorithms only care about meters; SafeQ cares about **Energy**. By mapping hazards to a Hamiltonian landscape, I created a system where the "best" route is the one that minimizes physical stress on the vehicle. 

The core mathematical challenge was the **Weight Function**:
$$H = L + (R \times M \times S)$$
Where $L$ is length, $R$ is risk severity, $M$ is the multiplier (**2,000**), and $S$ is the vehicle sensitivity. This equation ensures that the "Path of Least Resistance" is always the safest one.

---

### 🎯 System Architecture

* **`engine.py`** – The "Brain." Manages the Hamiltonian solver and graph-weight recalibration.
* **`detector.py`** – The "Eyes." Bridges the physical world to the digital twin using YOLOv8 detections.
* **`app.py`** – The "Command Center." Handles session state, real-time map rendering, and the Streamlit UI.
* **`auth.py`** – The "Gatekeeper." Manages user authentication and specific vehicle profile loading.

---

### 🚦 Running the Project

1.  **Clone the Repository**
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Build the Digital Twin**: 
    Enter "Kochi, Kerala, India" in the sidebar and click **Build Graph**.
4.  **Launch Dashboard**:
    ```bash
    streamlit run app.py
    ```

---

### 🎞️ Preview

> **Comparison View**: Note how the Green Line swerves to avoid the Pothole Cluster (Orange Marker) while the Red Line ignores it.