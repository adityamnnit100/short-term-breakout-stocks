Environment and compatibility notes

- Recommended Python: 3.8 (tested) — minimal; Python 3.9+ recommended if available.
- Pinned packages to avoid typing incompatibilities:
  - multitasking==0.0.10  # required to avoid "'type' object is not subscriptable" on Python 3.8
  - yfinance>=0.2.0,<0.3.0

Notes:
- The app uses Streamlit + Plotly for UI. If you see import-time typing errors originating from `multitasking`, reinstall pinned versions:

```bash
pip install -r requirements.txt
pip install multitasking==0.0.10
```

- If you plan to upgrade Python (recommended), test `multitasking` and `yfinance` after upgrading.

Compatibility notes:
- SciPy: pinned to `1.10.1` for Python 3.8 compatibility. If you upgrade to Python 3.9+, you can try newer SciPy releases.
