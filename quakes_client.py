"""A small client for the USGS Earthquake Catalog API.

This module is plain Python. It has no dependency on jsonargparse and no
knowledge that it will be exposed as a command line tool. All it does is have
well named parameters, accurate type hints and docstrings describing them.

API reference: https://earthquake.usgs.gov/fdsnws/event/1/
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USGS_URL = "https://earthquake.usgs.gov"
KM_PER_MILE = 1.609344
MAGNITUDE_BANDS = [
    ("minor 2.0-3.9", 2.0, 3.9),
    ("light 4.0-4.9", 4.0, 4.9),
    ("moderate 5.0-5.9", 5.0, 5.9),
    ("strong 6.0-6.9", 6.0, 6.9),
    ("major 7.0+", 7.0, None),
]


class CatalogError(Exception):
    """Raised when the catalog rejects a request."""


@dataclass
class Area:
    """Circular region of the globe to restrict a search to.

    Args:
        latitude: Latitude of the center, in degrees, positive towards north.
        longitude: Longitude of the center, in degrees, positive towards east.
        radius: Radius around the center, in the distance unit of the client.
    """

    latitude: float
    longitude: float
    radius: float = 500.0


@dataclass
class Quake:
    """Summary of a single seismic event."""

    time: datetime
    magnitude: float
    depth: float
    latitude: float
    longitude: float
    id: str
    place: str


class EarthquakeCatalog:
    """Client for the earthquake catalog of the U.S. Geological Survey."""

    def __init__(
        self,
        distance_unit: Literal["km", "mi"] = "km",
        min_magnitude: float = 2.5,
        timeout: float = 30.0,
    ):
        """Initialize the client.

        Args:
            distance_unit: Unit used for all distances, both given and returned.
            min_magnitude: Magnitude below which events are ignored by default.
            timeout: Seconds to wait for a response before giving up.
        """
        self.distance_unit = distance_unit
        self.min_magnitude = min_magnitude
        self.timeout = timeout

    def search(
        self,
        start: date | None = None,
        end: date | None = None,
        min_magnitude: float | None = None,
        max_magnitude: float | None = None,
        area: Area | None = None,
        order_by: Literal["time", "time-asc", "magnitude", "magnitude-asc"] = "time",
        limit: int = 20,
    ) -> list[Quake]:
        """Search the catalog for events matching the given criteria.

        Args:
            start: Only events at or after this date. Defaults to 30 days ago.
            end: Only events at or before this date. Defaults to now.
            min_magnitude: Only events at or above this magnitude. Defaults to
                the value given to the client.
            max_magnitude: Only events at or below this magnitude.
            area: Only events within this region of the globe.
            order_by: Order in which the events are returned.
            limit: Maximum number of events to return.

        Returns:
            The matching events, at most ``limit`` of them.
        """
        params = self._filters(start, end, min_magnitude, max_magnitude, area)
        data = self._get("/fdsnws/event/1/query", **params, orderby=order_by, limit=limit)
        return [self._to_quake(feature) for feature in data["features"]]

    def count(
        self,
        start: date | None = None,
        end: date | None = None,
        min_magnitude: float | None = None,
        max_magnitude: float | None = None,
        area: Area | None = None,
    ) -> int:
        """Count the events matching the given criteria, without fetching them.

        Args:
            start: Only events at or after this date. Defaults to 30 days ago.
            end: Only events at or before this date. Defaults to now.
            min_magnitude: Only events at or above this magnitude. Defaults to
                the value given to the client.
            max_magnitude: Only events at or below this magnitude.
            area: Only events within this region of the globe.

        Returns:
            The number of matching events.
        """
        params = self._filters(start, end, min_magnitude, max_magnitude, area)
        return self._get("/fdsnws/event/1/count", **params)["count"]

    def event(self, event_id: str) -> dict:
        """Get everything the catalog knows about a single event.

        Args:
            event_id: Identifier of the event, e.g. ``us7000srb1``.

        Returns:
            The details of the event, with the field names the catalog uses.
        """
        data = self._get("/fdsnws/event/1/query", eventid=event_id)
        details = {"id": data["id"], **data["properties"]}
        details.pop("products", None)  # megabytes of derived data, not of interest here
        return details

    def feed(
        self,
        level: Literal["significant", "4.5", "2.5", "1.0", "all"] = "significant",
        period: Literal["hour", "day", "week", "month"] = "day",
    ) -> list[Quake]:
        """Get one of the real time feeds of recent events.

        Unlike :meth:`search`, feeds are precomputed by the USGS and updated
        every minute, so they are the fastest way to see what is happening now.

        Args:
            level: Which events the feed includes. Either those flagged as
                significant, or all those at or above a given magnitude.
            period: How far back the feed goes.

        Returns:
            The events currently in the feed, most recent first.
        """
        data = self._get(f"/earthquakes/feed/v1.0/summary/{level}_{period}.geojson")
        return [self._to_quake(feature) for feature in data["features"]]

    def summary(
        self,
        start: date | None = None,
        end: date | None = None,
        area: Area | None = None,
    ) -> dict:
        """Summarize the seismic activity of a period as aggregated statistics.

        Args:
            start: Beginning of the period. Defaults to 30 days ago.
            end: End of the period. Defaults to now.
            area: Restrict the summary to this region of the globe.

        Returns:
            How many events happened in each magnitude band, and the strongest
            one of the period.
        """
        by_band = {name: self.count(start, end, low, high, area) for name, low, high in MAGNITUDE_BANDS}
        strongest = self.search(start, end, area=area, order_by="magnitude", limit=1)
        return {
            "start": (start or self._month_ago()).isoformat(),
            "end": (end or datetime.now(timezone.utc).date()).isoformat(),
            "total": sum(by_band.values()),
            "by_magnitude": by_band,
            "strongest": vars(strongest[0]) if strongest else None,
        }

    def _month_ago(self) -> date:
        return (datetime.now(timezone.utc) - timedelta(days=30)).date()

    def _filters(
        self,
        start: date | None,
        end: date | None,
        min_magnitude: float | None,
        max_magnitude: float | None,
        area: Area | None,
    ) -> dict:
        params = {
            "starttime": (start or self._month_ago()).isoformat(),
            "minmagnitude": self.min_magnitude if min_magnitude is None else min_magnitude,
        }
        if end is not None:
            params["endtime"] = end.isoformat()
        if max_magnitude is not None:
            params["maxmagnitude"] = max_magnitude
        if area is not None:
            radius = area.radius if self.distance_unit == "km" else area.radius * KM_PER_MILE
            params.update(latitude=area.latitude, longitude=area.longitude, maxradiuskm=radius)
        return params

    def _get(self, path: str, **params) -> dict:
        url = f"{USGS_URL}{path}?{urlencode({'format': 'geojson', **params})}"
        try:
            with urlopen(Request(url), timeout=self.timeout) as response:
                return json.loads(response.read())
        except HTTPError as ex:
            reported = ex.read().decode(errors="replace").strip().splitlines()
            raise CatalogError(f"{reported[0] if reported else ex.reason} (requesting {path})") from ex

    def _to_quake(self, feature: dict) -> Quake:
        properties = feature["properties"]
        longitude, latitude, depth = feature["geometry"]["coordinates"]
        return Quake(
            time=datetime.fromtimestamp(properties["time"] / 1000, tz=timezone.utc),
            magnitude=round(properties["mag"], 2),
            depth=round(depth if self.distance_unit == "km" else depth / KM_PER_MILE, 2),
            latitude=round(latitude, 4),
            longitude=round(longitude, 4),
            id=feature["id"],
            place=properties["place"] or "",
        )
