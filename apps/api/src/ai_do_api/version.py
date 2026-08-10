import os


VERSION = "0.1.1"
# Captured once at process import so a checkout moving underneath a stale
# process cannot make that process appear to run the new revision.
RUNTIME_REVISION = os.environ.get("AI_DO_RUNTIME_REVISION", "").strip() or "unmanaged"
