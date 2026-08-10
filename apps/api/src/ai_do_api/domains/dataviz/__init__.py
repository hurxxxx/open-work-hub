"""Data visualization domain.

Ports the legacy Flask "08_data_viz" core-measurement viewer: reads the
hand-curated "코어 측정값 정리" Excel summary (rotor/stator dimensional
measurements per model, with spec/tolerance) and returns plot-ready JSON.
Charts are rendered client-side with react-plotly.js.
"""
