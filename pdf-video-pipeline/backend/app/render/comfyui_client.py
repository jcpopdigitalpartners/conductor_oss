from __future__ import annotations

import json
from urllib import parse as urllib_parse
from urllib import request as urllib_request


class ComfyUIClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def submit_prompt(self, prompt: dict) -> str:
        request = urllib_request.Request(
            f"{self.base_url}/prompt",
            data=json.dumps({"prompt": prompt}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        prompt_id = body.get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return a prompt_id")
        return str(prompt_id)

    def get_history(self, prompt_id: str) -> dict:
        with urllib_request.urlopen(f"{self.base_url}/history/{prompt_id}", timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_output(self, *, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        query = urllib_parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": folder_type}
        )
        with urllib_request.urlopen(f"{self.base_url}/view?{query}", timeout=60) as response:
            return response.read()
