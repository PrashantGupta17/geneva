from utils.storage import StorageManager
import os

storage = StorageManager(threshold=10)
long_payload = "This is a very long payload that exceeds the threshold of 10 bytes."
short_payload = "Short."

res_long = storage.persist_if_large(long_payload)
res_short = storage.persist_if_large(short_payload)

print(f"Long Payload Result: {res_long}")
print(f"Short Payload Result: {res_short}")

if res_long.startswith("path://") and os.path.exists(res_long[7:]):
    with open(res_long[7:], 'r') as f:
        content = f.read()
    if content == long_payload:
        print("Test passed: Long payload successfully written to disk and URI returned.")
    else:
        print("Test failed: Content mismatch.")
else:
    print("Test failed: Long payload did not return correct path URI or file does not exist.")

if res_short == short_payload:
    print("Test passed: Short payload correctly returned as-is.")
else:
    print("Test failed: Short payload was modified.")
