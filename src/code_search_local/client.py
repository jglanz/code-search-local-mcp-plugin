"""Small HTTP client; importing it never imports model or index libraries."""

import aiohttp

from .service import token_for


class Client:
    def __init__(self, settings):
        self.settings = settings

    async def request(self, method, path, *, data=None, params=None):
        headers = {"Authorization": "Bearer " + token_for(self.settings.root)}
        timeout = aiohttp.ClientTimeout(total=None, connect=5, sock_read=None)
        try:
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.request(
                    method, self.settings.url + path, json=data, params=params
                ) as response:
                    result = await response.json()
                    if response.status >= 400:
                        raise RuntimeError(result.get("error", f"HTTP {response.status}"))
                    return result
        except aiohttp.ClientError as error:
            raise OSError(f"Cannot connect to {self.settings.url}: {error}") from error

    async def stats(self, project=None):
        return await self.request(
            "GET", "/api/v1/stats", params={"project": project} if project else None
        )
