import asyncio
from collections import Counter
from contextlib import suppress

import aiohttp
import requests

TIMEOUT = 5
template = "https://{host}/status?json=true"

requests.packages.urllib3.disable_warnings()


async def fetch(session, url):
    with suppress(Exception):
        async with session.get(url, ssl=False, timeout=TIMEOUT) as response:
            response = await response.json()
            return response["version"]
    return "unknown"


async def main():

    url = template.format(host="mainnet.nucypher.network:9151")
    async with aiohttp.ClientSession() as session:
        async with session.get(url, ssl=False, timeout=TIMEOUT) as response:
            status_data = await response.json()

        nodes = status_data.get("known_nodes", [])
        total_nodes = len(nodes)
        print(f"Number of nodes: {total_nodes}")

        tasks = set()
        for node in nodes:
            url = template.format(host=node["rest_url"])
            tasks.add(fetch(session, url))

        results = Counter()
        for task in asyncio.as_completed(tasks):
            if task:
                result = await task
                results[result] += 1

        items = sorted(results.items(), key=lambda result: result[1], reverse=True)
        for version, count in items:
            print(f"Version {version}: {count} nodes ({count*100/total_nodes:.1f}%)")


asyncio.run(main())
