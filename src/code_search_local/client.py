"""Small HTTP client; importing it never imports model or index libraries."""

import aiohttp

from code_search_local import constants

from .service import token_for


class Client:
    def __init__(self, settings):
        self.settings = settings

    async def request(self, method, path, *, data=None, params=None):
        headers = {
            constants.KEY_AUTHORIZATION: constants.HTTP_BEARER + token_for(self.settings.root)
        }
        timeout = aiohttp.ClientTimeout(
            total=None, connect=constants.HEALTH_PROBE_TIMEOUT_SECONDS, sock_read=None
        )
        try:
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.request(
                    method, self.settings.url + path, json=data, params=params
                ) as response:
                    result = await response.json()
                    if response.status >= constants.HTTP_BAD_REQUEST:
                        raise RuntimeError(
                            result.get(constants.KEY_ERROR, f"HTTP {response.status}")
                        )
                    return result
        except aiohttp.ClientError as error:
            raise OSError(f"Cannot connect to {self.settings.url}: {error}") from error

    async def stats(self, project=None):
        return await self.request(
            constants.HTTP_GET,
            constants.STATS_ENDPOINT,
            params={constants.KEY_PROJECT: project} if project else None,
        )
