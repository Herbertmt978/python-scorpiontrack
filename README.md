# pyscorpiontrack

[![CI](https://github.com/Herbertmt978/python-scorpiontrack/actions/workflows/ci.yml/badge.svg)](https://github.com/Herbertmt978/python-scorpiontrack/actions/workflows/ci.yml)

`pyscorpiontrack` is a small async Python client for ScorpionTrack shared-location links.

This package exists to support a clean Home Assistant Core integration for the public ScorpionTrack share-link flow. It intentionally focuses on the read-only location-share endpoint rather than the private authenticated portal path.

## Scope

- accepts either a raw ScorpionTrack share token or a full shared-location URL
- fetches the active share payload from the same endpoint the ScorpionTrack share page uses
- normalizes shares, vehicles, and position data into typed dataclasses
- raises explicit exceptions for connectivity problems, invalid tokens, and expired or unavailable shares

## Example

```python
from aiohttp import ClientSession
from pyscorpiontrack import ScorpionTrackClient


async def main() -> None:
    async with ClientSession() as session:
        client = ScorpionTrackClient(session=session, token="YOUR_SHARE_TOKEN")
        share = await client.async_get_share()
        print(share.title)
        for vehicle in share.vehicles:
            print(vehicle.display_name, vehicle.status)
```

## Why this repo exists

Home Assistant Core expects service communication to live in an external Python library. This package is the extraction of the ScorpionTrack share-link logic into a reusable dependency so the Home Assistant integration can stay focused on config flows, entities, diagnostics, and platform behavior.
