import os
import uuid
import yaml

class StorageManager:
    def __init__(self, config_path: str = "geneva_config.yaml", threshold: int = 1000):
        self.threshold = threshold
        self.storage_type = "LocalStorage"
        self.storage_path = "./storage"

        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}
                storage_cfg = config.get("storage", {})
                if storage_cfg:
                    self.storage_type = storage_cfg.get("type", "LocalStorage")
                    self.storage_path = storage_cfg.get("path", "./storage")

        os.makedirs(self.storage_path, exist_ok=True)

    def persist_if_large(self, payload: str) -> str:
        """
        If payload length > threshold, save it to disk and return a URI instead of the raw data.
        Otherwise, return the payload as is.
        """
        if len(payload) > self.threshold:
            filename = f"payload_{uuid.uuid4().hex}.txt"
            filepath = os.path.join(self.storage_path, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(payload)

            print(f"[Storage] Payload exceeds threshold ({len(payload)} > {self.threshold}). Saved to {filepath}")
            return f"path://{filepath}"

        return payload
