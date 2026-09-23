<div align="center">

<img src="https://raw.githubusercontent.com/Herbertmt978/python-scorpiontrack/main/brand/header.svg" alt="pyscorpiontrack wordmark with a shared location pin" width="760">

# pyscorpiontrack

An asynchronous Python client for ScorpionTrack shared-location links.

[![CI](https://github.com/Herbertmt978/python-scorpiontrack/actions/workflows/ci.yml/badge.svg)](https://github.com/Herbertmt978/python-scorpiontrack/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyscorpiontrack?color=0EA5E9)](https://pypi.org/project/pyscorpiontrack/)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
[![License: MIT](https://img.shields.io/badge/License-MIT-0F766E.svg)](LICENSE)

[Install](#install) | [Quick start](#quick-start) | [Returned data](#returned-data) | [Errors](#errors) | [Privacy](#scope-and-privacy) | [Development](#development)

</div>

`pyscorpiontrack` fetches the read-only data behind a ScorpionTrack
shared-location link and turns it into typed, frozen Python objects. It was
created as the service client for a Home Assistant Core integration, but can be
used by any asynchronous Python application.

## Install

Python 3.12 or newer is required.

```bash
python -m pip install pyscorpiontrack
```

## Quick start

Pass either a raw share token or a shared-location URL containing a `token`
query parameter. The client extracts the token from a URL; use a link from a
trusted source.

```python
import asyncio
import os

from aiohttp import ClientSession
from pyscorpiontrack import ScorpionTrackClient


async def main() -> None:
    share_link = os.environ["SCORPIONTRACK_SHARE_LINK"]
    async with ClientSession() as session:
        client = ScorpionTrackClient(session=session, token=share_link)
        share = await client.async_get_share()

    print(share.title)
    for vehicle in share.vehicles:
        print(vehicle.display_name, vehicle.status, vehicle.position.timestamp)


asyncio.run(main())
```

The caller owns the `aiohttp.ClientSession` and decides when to refresh. Each
`async_get_share()` call fetches the latest share payload with a 10-second
timeout by default.

## Returned data

| Model | Useful fields |
| --- | --- |
| `ScorpionTrackShare` | Share title, owner name, expiry, distance units, and a tuple of vehicles. |
| `ScorpionTrackVehicle` | Display name, registration, make/model, latest position, and derived status. |
| `ScorpionTrackPosition` | Coordinates, timestamp, speed in km/h, ignition, bearing, and address when supplied. |

The status is derived from the latest speed and ignition values: `moving`,
`idle`, `parked`, or `unknown`. Each vehicle always has a
`ScorpionTrackPosition` object, but individual values such as its timestamp may
be `None`. `ScorpionTrackShare.convert_speed()` converts a km/h value to the
share's preferred distance unit.

## Errors

| Exception | Meaning |
| --- | --- |
| `ScorpionTrackInvalidTokenError` | No token was supplied, the URL had no token parameter, or the API rejected the token. |
| `ScorpionTrackShareUnavailableError` | The share was not found, expired, revoked, or returned no data. |
| `ScorpionTrackConnectionError` | The request failed, timed out, or returned invalid data. |

All three derive from `ScorpionTrackError` for callers that need one catch point.

## Scope and privacy

The library uses the shared-location endpoint, not ScorpionTrack's private
authenticated portal. It cannot create shares, change vehicle settings, or
control a tracker. A share token grants access to location data; protect the
token, share URL, returned coordinates, and logs. Do not include them in public
issues.

The package is independent of ScorpionTrack. Use
[GitHub Issues](https://github.com/Herbertmt978/python-scorpiontrack/issues)
for reproducible library problems.

## Development

From a checkout with the development dependencies installed:

```bash
python -m pytest tests -q
python -m build
```

The package is released under the [MIT licence](LICENSE).
