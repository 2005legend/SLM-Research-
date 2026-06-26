# Task: Fix divide() so it raises ZeroDivisionError instead of Value

**Status**: ✓ Applied

**Task**: Fix divide() so it raises ZeroDivisionError instead of ValueError

**Plan**:
- 1. Open the file containing the `divide()` function.
- 2. Locate the current implementation of the `divide()` function.
- 3. Identify the line where division occurs and check if it includes error handling for division by zero.
- 4. If the code checks for division by zero using a condition, replace that condition with a `try-except` block.
- 5. Within the `except` block, catch the `ZeroDivisionError`.
- 6. If the current implementation uses a custom exception for division by zero (e.g., `ValueError`), remove the custom exception handling and ensure only `ZeroDivisionError` is caught.
- 7. Ensure that within the `except` block, a `ZeroDivisionError` is raised with an appropriate error message.
- 8. Save the changes to the file.
- 9. Test the `divide()` function to verify that it now correctly raises a `ZeroDivisionError` when attempting to divide by zero.
- 10. Commit and push the changes to the version control system if applicable.

**Patch** (first 500 chars):
```diff
--- a/simple_api/core.py
+++ b/simple_api/core.py
@@ -7,4 +7,7 @@
     Raises:
         ZeroDivisionError: When *b* is zero.
     """
-    return a / b
+    try:
+        return a / b
+    except ZeroDivisionError as e:
+        raise ZeroDivisionError("Cannot divide by zero") from e

```
