from pathlib import Path

patch = '''--- a/local_sage/config.py
+++ b/local_sage/config.py
@@ -1,4 +1,4 @@
-"""Configuration management for local-sage.
+"""Configuration management for local-sage — patched by sage validate test.
 
 Loads ``SageConfig`` from (in priority order):
 1. Environment variables prefixed with ``SAGE_`` (highest priority).
'''

Path("test_patch.diff").write_text(patch, encoding="utf-8")
print("patch written")
