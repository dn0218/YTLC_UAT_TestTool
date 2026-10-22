"""REST API client for the OCS job server."""
import requests

from core.config import AppConfig
from core.errors import ApiConnectionError


class JobApiClient:
    """Client for the jobservermgr trigger API."""

    def __init__(self, config: AppConfig):
        self._config = config
        # The params string contains '|' and other reserved characters; the
        # job server's servlet decodes URL-encoded values, so always encode.
        self._session = requests.Session()

    def trigger_job(self, job_name: str, params: str, job_group: str = "InvoiceManagement",
                    on_log=None):
        """POST /jobservermgr/api/triggerJob and return the Response."""
        from urllib.parse import quote
        encoded_params = quote(params, safe="")
        url = (f"{self._config.api_base_url}/jobservermgr/api/triggerJob"
               f"?jobName={job_name}&jobGroup={job_group}&params={encoded_params}")
        if on_log:
            on_log(f"Triggering API: {url}")
        try:
            percent = 0  # keep a hook for future progress reporting
            response = self._session.post(url, timeout=30)
            if on_log:
                on_log(f"API response status: {response.status_code}, body: {response.text}")
            response.raise_for_status()
            return response
        except Exception as e:
            raise ApiConnectionError(f"API call failed: {e}") from e
