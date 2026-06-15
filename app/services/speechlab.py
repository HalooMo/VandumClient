import requests
from flask import current_app


class SpeechLabClient:
    def __init__(self, base_url=None, api_key=None):
        self.base_url = (base_url or current_app.config["SPEECHLAB_BASE_URL"]).rstrip("/")
        self.api_key = (api_key or current_app.config.get("SPEECHLAB_API_KEY") or "").strip()
        if not self.api_key:
            raise ValueError("SPEECHLAB_API_KEY не задан. Добавьте ключ в .env и перезапустите сервер.")
        self.headers = {"X-API-Key": self.api_key}

    def health(self, timeout=30):
        r = requests.get(f"{self.base_url}/health", timeout=timeout)
        r.raise_for_status()
        return r.json()

    def create_dub(self, data, files=None):
        r = requests.post(
            f"{self.base_url}/api/v1/dub",
            headers=self.headers,
            data=data,
            files=files,
            timeout=600,
        )
        return r

    def get_job(self, job_id):
        r = requests.get(
            f"{self.base_url}/api/v1/jobs/{job_id}",
            headers=self.headers,
            timeout=60,
        )
        return r

    def list_jobs(self):
        r = requests.get(
            f"{self.base_url}/api/v1/jobs",
            headers=self.headers,
            timeout=60,
        )
        return r

    def download_job(self, job_id):
        r = requests.get(
            f"{self.base_url}/api/v1/jobs/{job_id}/download",
            headers=self.headers,
            stream=True,
            timeout=600,
        )
        return r

    def create_dub_json(self, data):
        r = requests.post(
            f"{self.base_url}/api/v1/dub",
            headers={**self.headers, "Content-Type": "application/json"},
            json=data,
            timeout=600,
        )
        return r
