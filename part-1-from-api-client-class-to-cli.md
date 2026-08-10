# From API client to CLI, without writing a parser

At some point most of us write a class that wraps an HTTP API. The constructor takes the things that do not change between calls: the base URL, the credentials, the timeout, a few defaults. The methods are the endpoints.

Then comes the day you want to call it from a terminal. To check one thing quickly, to put it in a cron job, or to hand it to a colleague who does not write Python. The usual answer is an `argparse` layer that spells out every parameter a third time, after the signature and after the docstring. It is tedious to write, and it goes stale the moment someone adds a parameter to the client and forgets the CLI.

[jsonargparse](https://github.com/mauvilsa/jsonargparse) can derive that layer from the class itself. The signature already says what the parameters are and what types they take. The docstring already says what they mean. That is all a command line parser needs to know, so `auto_cli` reads it from there:

```python
auto_cli(EarthquakeCatalog)
```

This post builds such a client from scratch, a few lines at a time, and every snippet runs as it is written. The API is the [USGS Earthquake Catalog](https://earthquake.usgs.gov/fdsnws/event/1/), the service of the U.S. Geological Survey that publishes every seismic event recorded around the world, updated every minute. It needs no key, no account and no registration, so you can paste the code and get real data back. The catalog is live, so the numbers you get will not be exactly the ones shown here.

If you already have a client class of your own, it will probably need no change at all beyond making sure its type hints and docstrings are complete. Feel free to read the snippets below as a description of what your own class would do.

You will need Python 3.10 or later and:

```bash
pip install "jsonargparse[signatures]"
```

## A client small enough to paste

Here is the whole first version. One constructor, one method, and a small private helper that performs the request:

```python
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import urlopen


def since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class EarthquakeCatalog:
    """Client for the earthquake catalog of the U.S. Geological Survey."""

    def __init__(self, min_magnitude: float = 2.5, timeout: float = 30.0):
        """
        Args:
            min_magnitude: Magnitude below which events are ignored by default.
            timeout: Seconds to wait for a response before giving up.
        """
        self.min_magnitude = min_magnitude
        self.timeout = timeout

    def count(self, days: int = 30, min_magnitude: float | None = None) -> int:
        """Count the events recorded over the last few days.

        Args:
            days: How far back to look.
            min_magnitude: Only events at or above this magnitude. Defaults to
                the value given to the client.

        Returns:
            The number of matching events.
        """
        data = self._get(
            "/fdsnws/event/1/count",
            starttime=since(days),
            minmagnitude=self.min_magnitude if min_magnitude is None else min_magnitude,
        )
        return data["count"]

    def _get(self, path: str, **params) -> dict:
        url = f"https://earthquake.usgs.gov{path}?{urlencode({'format': 'geojson', **params})}"
        with urlopen(url, timeout=self.timeout) as response:
            return json.loads(response.read())


if __name__ == "__main__":
    from jsonargparse import auto_cli

    print(auto_cli(EarthquakeCatalog))
```

Nothing in the class knows about command lines. The last three lines are the entire interface. Save it as `quakes.py` and ask it for help:

```
$ python quakes.py --help
usage: quakes.py [--config CONFIG] [--min_magnitude MIN_MAGNITUDE]
                 [--timeout TIMEOUT]
                 {count} ...

Client for the earthquake catalog of the U.S. Geological Survey:
  --min_magnitude MIN_MAGNITUDE
                        Magnitude below which events are ignored by default.
                        (type: float, default: 2.5)
  --timeout TIMEOUT     Seconds to wait for a response before giving up.
                        (type: float, default: 30.0)

  Available subcommands:
                        (required)
    count               Count the events recorded over the last few days.
```

The shape of the class is the shape of the command line. Constructor parameters became options that come before the subcommand, public methods became the subcommands, and the class docstring became the description. Ask about the subcommand and the same thing happened one level down:

```
$ python quakes.py count --help
usage: quakes.py [options] count [--config CONFIG] [--days DAYS]
                                 [--min_magnitude MIN_MAGNITUDE]

Count the events recorded over the last few days.

options:
  --days DAYS           How far back to look. (type: int, default: 30)
  --min_magnitude MIN_MAGNITUDE
                        Only events at or above this magnitude. Defaults to
                        the value given to the client. (type: float | None,
                        default: null)
```

Every line of help text was written once, in the docstring, where it also serves anyone reading the code or the generated API documentation. The types were written once, in the signature, where they also serve the type checker.

So, how many earthquakes of magnitude 5 or above were there last week?

```
$ python quakes.py count --days=7 --min_magnitude=5
67
```

Note that `min_magnitude` appears in two places, and means something slightly different in each. Before the subcommand it is the client's standing default; after it, the value for this one call. That distinction was expressed only by where the parameter lives in the class, and it survives into the CLI:

```
$ python quakes.py --min_magnitude=6 count --days=7
1
```

## A second endpoint

Counting is a thin thing to do with a catalog of earthquakes. Let us fetch the events themselves, with a real filter: only those within a given distance of a point on the globe.

That filter has three numbers that belong together, so it deserves a small record of its own. The events coming back deserve one too. Add `from dataclasses import dataclass` and `from typing import Literal` to the imports, then these:

```python
@dataclass
class Area:
    """Circular region of the globe to restrict a search to.

    Args:
        latitude: Latitude of the center, in degrees, positive towards north.
        longitude: Longitude of the center, in degrees, positive towards east.
        radius: Radius around the center, in kilometers.
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


def to_quake(feature: dict) -> Quake:
    properties = feature["properties"]
    longitude, latitude, depth = feature["geometry"]["coordinates"]
    return Quake(
        time=datetime.fromtimestamp(properties["time"] / 1000, tz=timezone.utc),
        magnitude=properties["mag"],
        depth=depth,
        latitude=latitude,
        longitude=longitude,
        id=feature["id"],
        place=properties["place"],
    )
```

And the method itself, next to `count`:

```python
    def search(
        self,
        days: int = 30,
        min_magnitude: float | None = None,
        area: Area | None = None,
        order_by: Literal["time", "time-asc", "magnitude", "magnitude-asc"] = "time",
        limit: int = 10,
    ) -> list[Quake]:
        """Search the catalog for events matching the given criteria.

        Args:
            days: How far back to look.
            min_magnitude: Only events at or above this magnitude. Defaults to
                the value given to the client.
            area: Only events within this region of the globe.
            order_by: Order in which the events are returned.
            limit: Maximum number of events to return.

        Returns:
            The matching events, at most ``limit`` of them.
        """
        within = {}
        if area is not None:
            within = {
                "latitude": area.latitude,
                "longitude": area.longitude,
                "maxradiuskm": area.radius,
            }
        data = self._get(
            "/fdsnws/event/1/query",
            starttime=since(days),
            minmagnitude=self.min_magnitude if min_magnitude is None else min_magnitude,
            orderby=order_by,
            limit=limit,
            **within,
        )
        return [to_quake(feature) for feature in data["features"]]
```

Two of these parameters are more interesting than a number or a string, and the CLI treats both of them accordingly:

```
$ python quakes.py search --help
usage: quakes.py [options] search [--config CONFIG] [--days DAYS]
                                  [--min_magnitude MIN_MAGNITUDE]
                                  [--area AREA]
                                  [--order_by {time,time-asc,magnitude,magnitude-asc}]
                                  [--limit LIMIT]

options:
  --days DAYS           How far back to look. (type: int, default: 30)
  --min_magnitude MIN_MAGNITUDE
                        Only events at or above this magnitude. Defaults to
                        the value given to the client. (type: float | None,
                        default: null)
  --area.help           Show the help for Area and exit.
  --area AREA           Only events within this region of the globe. (type:
                        Area | None, default: null)
  --order_by {time,time-asc,magnitude,magnitude-asc}
                        Order in which the events are returned. (type:
                        Literal['time', 'time-asc', 'magnitude', 'magnitude-
                        asc'], default: time)
  --limit LIMIT         Maximum number of events to return. (type: int,
                        default: 10)
```

`order_by` is a `Literal`, so its four values became the accepted choices. Anything else is rejected with the list of what is allowed, before a request is made.

`area` is a whole object, so it got a help page of its own, built from the dataclass the same way the main help was built from the client:

```
$ python quakes.py search --area.help
usage: quakes.py --area.latitude LATITUDE --area.longitude LONGITUDE
                 [--area.radius RADIUS]

Circular region of the globe to restrict a search to:
  --area.latitude LATITUDE
                        Latitude of the center, in degrees, positive towards
                        north. (required, type: float)
  --area.longitude LONGITUDE
                        Longitude of the center, in degrees, positive towards
                        east. (required, type: float)
  --area.radius RADIUS  Radius around the center, in kilometers. (type: float,
                        default: 500.0)
```

Its fields are set individually, with a dot:

```bash
python quakes.py search --area.latitude=35.68 --area.longitude=139.69 --area.radius=300 \
                    --min_magnitude=5 --days=365 --order_by=magnitude --limit=3
```

Nothing had to be registered or declared for that to work. The parameter is typed `Area | None`, and `Area` is an ordinary dataclass, which is enough.

## Printing what comes back

The command above does work, but what it prints is not pleasant:

```
[Quake(time=datetime.datetime(2025, 10, 4, 15, 21, 10, 42000, tzinfo=datetime.timezone.utc), magnitude=5.9, depth=54.164, latitude=37.4213, longitude=141.5524, id='us6000resn', place='48 km ENE of Tomioka, Japan'), Quake(time=datetime.datetime(2026, 6, 26, 3, 46, 35, 798000, ...
```

`auto_cli` deliberately does not print anything itself. It returns whatever the method returned and lets you decide, which is the one place where a command line tool does need code of its own. The methods have return type hints, so the decision can be made once, for all of them:

```python
def render(result) -> str:
    """Render a value returned by a client method as text for a terminal."""
    if isinstance(result, (str, int, float)):
        return str(result)
    if isinstance(result, list) and result and is_dataclass(result[0]):
        return render_table(result)
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


def render_table(records: list) -> str:
    """Render a list of dataclass instances as a table with aligned columns."""
    columns = [field.name for field in fields(records[0])]
    rows = [columns] + [[cell(getattr(record, column)) for column in columns] for record in records]
    widths = [max(len(row[index]) for row in rows) for index in range(len(columns))]
    return "\n".join("  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip() for row in rows)


def cell(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if isinstance(value, datetime) else str(value)
```

Import `fields` and `is_dataclass` from `dataclasses` alongside `dataclass`, and wrap the call:

```python
if __name__ == "__main__":
    from jsonargparse import auto_cli

    print(render(auto_cli(EarthquakeCatalog)))
```

A list of records is a table whose columns are the fields of the record:

```
$ python quakes.py search --area.latitude=35.68 --area.longitude=139.69 --area.radius=300 \
                      --min_magnitude=5 --days=365 --order_by=magnitude --limit=3
time              magnitude  depth   latitude  longitude  id          place
2025-10-04 15:21  5.9        54.164  37.4213   141.5524   us6000resn  48 km ENE of Tomioka, Japan
2026-06-26 03:46  5.8        43      35.6907   140.5771   us6000t8cy  2 km ESE of Yōkaichiba, Japan
2026-06-16 10:46  5.3        63.617  36.1715   139.6995   us7000std7  2 km SW of Koga, Japan
```

A number is still just a number, undecorated rather than quoted or wrapped in JSON:

```
$ python quakes.py count --days=7 --min_magnitude=5
67
```

Anything else falls through to indented JSON. Adding a method that returns a `dict` needs no new printing code, which is the point of dispatching on the type rather than on the subcommand.

## The rest of the client

The complete version of this client lives in [this repository](https://github.com/mauvilsa/blog-earthquake-cli), split into `quakes_client.py` for the client and `quakes_cli.py` for the interface. It is about three hundred lines across the two files, most of them docstrings. Beyond what is above it has:

- `event(event_id)`, the full record of one event, returned as the `dict` the catalog itself provides.
- `feed(level, period)`, the USGS real time feeds, which are precomputed and so the fastest way to see what is happening right now.
- `summary(start, end, area)`, aggregated statistics that the client computes out of several requests.
- Real `start` and `end` dates instead of a `days` count.
- A `distance_unit` on the client that converts both the radius you give and the depths you get back.
- Errors from the API turned into one readable line.

Its help is the same shape as the small one, just longer:

```
$ python quakes_cli.py --help
usage: quakes_cli.py [--config CONFIG] [--distance_unit {km,mi}]
                     [--min_magnitude MIN_MAGNITUDE] [--timeout TIMEOUT]
                     {count,event,feed,search,summary} ...

Client for the earthquake catalog of the U.S. Geological Survey:
  --distance_unit {km,mi}
                        Unit used for all distances, both given and returned.
                        (type: Literal['km', 'mi'], default: km)
  --min_magnitude MIN_MAGNITUDE
                        Magnitude below which events are ignored by default.
                        (type: float, default: 2.5)
  --timeout TIMEOUT     Seconds to wait for a response before giving up.
                        (type: float, default: 30.0)

  Available subcommands:
    count               Count the events matching the given criteria, without
                        fetching them.
    event               Get everything the catalog knows about a single event.
    feed                Get one of the real time feeds of recent events.
    search              Search the catalog for events matching the given
                        criteria.
    summary             Summarize the seismic activity of a period as
                        aggregated statistics.
```

`event` takes an `event_id` with no default, so jsonargparse made it a positional argument rather than an option. If you would rather keep every parameter as a named option, pass `as_positional=False` to `auto_cli`.

```
$ python quakes_cli.py event us7000srb1
{
  "id": "us7000srb1",
  "mag": 7.8,
  "place": "25 km SW of Kablalan, Philippines",
  "time": 1780875461970,
  "updated": 1785641718662,
  "tz": null,
  "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000srb1",
  "felt": 581,
  "cdi": 9.1,
  "mmi": 8.53,
  "alert": "orange",
  "status": "reviewed",
  "tsunami": 0,
  "sig": 1529,
  "net": "us",
  "code": "7000srb1",
  "ids": ",us7000srb1,usauto7000srb1,",
  "sources": ",us,usauto,",
  "types": ",dyfi,finite-fault,general-text,ground-failure,impact-text,internal-moment-tensor,losspager,moment-tensor,origin,phase-data,shakemap,",
  "nst": 150,
  "dmin": 1.55,
  "rms": 0.5,
  "gap": 21,
  "magType": "mww",
  "type": "earthquake",
  "title": "M 7.8 - 25 km SW of Kablalan, Philippines"
}
```

That was the strongest of 2026 at the time of writing. `summary` returns a `dict` too, and prints the same way without a single line of code added for it:

```
$ python quakes_cli.py summary --start=2026-07-01 --end=2026-08-01
{
  "start": "2026-07-01",
  "end": "2026-08-01",
  "total": 3379,
  "by_magnitude": {
    "minor 2.0-3.9": 2240,
    "light 4.0-4.9": 919,
    "moderate 5.0-5.9": 209,
    "strong 6.0-6.9": 10,
    "major 7.0+": 1
  },
  "strongest": {
    "time": "2026-07-17 14:48:40.227000+00:00",
    "magnitude": 7.3,
    "depth": 22,
    "latitude": 14.6361,
    "longitude": -92.8969,
    "id": "us7000t1bu",
    "place": "52 km W of Puerto Madero, Mexico"
  }
}
```

The full client also uses `datetime.date` for `start` and `end`, which is a type jsonargparse does not handle out of the box. Rather than weakening the client's type hints to `str`, the CLI teaches the parser how to read and write that type, once:

```python
register_type(date, serializer=date.isoformat, deserializer=date.fromisoformat)
```

From then on `--start=2026-07-01` arrives at the client as a `date`, and a malformed one is rejected by the parser instead of by the API.

## The settings you do not want to retype

The client parameters are the ones you would get tired of typing: the endpoint, the timeout, the credentials. Every tool built with `auto_cli` accepts a `--config` file, so they can be written down once:

```yaml
# config.yaml
distance_unit: mi
min_magnitude: 4.0
timeout: 60.0
```

```bash
python quakes_cli.py --config config.yaml search --start=2026-07-01 --order_by=magnitude --limit=3
```

```
time              magnitude  depth  latitude  longitude  id          place
2026-07-17 14:48  7.3        13.67  14.6361   -92.8969   us7000t1bu  52 km W of Puerto Madero, Mexico
2026-07-28 07:27  6.8        6.21   32.6817   130.7217   us6000tgb9  2026 Uto, Japan Earthquake
2026-07-17 15:20  6.4        6.21   14.216    -93.2025   us7000t1cc  101 km WSW of Puerto Madero, Mexico
```

For an API that needs authentication this is the natural home for the token or the user name, in a file you can keep out of version control and give restrictive permissions, rather than in your shell history.

A config file can also cover a subcommand, by nesting its options under the subcommand's name:

```yaml
# config_japan.yaml
min_magnitude: 4.0

search:
  start: 2026-01-01
  order_by: magnitude
  limit: 5
  area:
    latitude: 36.2
    longitude: 138.25
    radius: 700
```

When it does, the subcommand does not have to be named on the command line either. The file is the whole invocation:

```
$ python quakes_cli.py --config config_japan.yaml
time              magnitude  depth  latitude  longitude  id          place
2026-04-20 07:52  7.4        25     39.971    143.0592   us6000sri7  102 km ENE of Miyako, Japan
2026-06-24 22:30  6.9        34     40.2745   142.1353   us6000t7zq  32 km ENE of Kuji, Japan
2026-05-15 11:22  6.7        42     38.9352   142.1579   us6000sxwq  41 km ESE of Ōfunato, Japan
2026-03-26 14:18  6.5        16     39.4377   143.3826   us7000s7u4  123 km E of Yamada, Japan
2026-07-01 12:08  6          35     40.2085   142.4411   us6000t9ej  54 km ENE of Noda, Japan
```

Arguments given on the command line still win, so `search --limit=2` after that would override the file. And `--print_config` dumps the settings a run would use, which is the least tedious way to start a new config file:

```
$ python quakes_cli.py --config config_japan.yaml search --print_config=skip_default
start: '2026-01-01'
area:
  latitude: 36.2
  longitude: 138.25
  radius: 700.0
order_by: magnitude
limit: 5
```

## Bringing your own client

If you already have a client class, the work is mostly checking that it says about itself what it already knows:

- Every parameter has a type hint, and the honest one. `date` rather than `str` for a date, `Literal` rather than `str` for something with four valid values, a small dataclass rather than three loose floats that belong together.
- Every parameter is described in the docstring, in a style [docstring_parser](https://pypi.org/project/docstring-parser/) understands, which covers the Google, Numpy, Sphinx and Epydoc conventions.
- Methods you do not want as subcommands start with an underscore.
- The constructor takes what does not change between calls. For most real APIs that means the credentials, and a config file already covers them. Passing `default_env=True` to `auto_cli` adds an environment variable for each one as well, again without the client having to read either.

Then the whole interface is one call, and it cannot fall out of step with the client, because there is nothing to keep in step.

The client, meanwhile, stays a plain class. It knows nothing about argparse, YAML, config files or terminals, and it is as pleasant to import from a notebook or a web service as it ever was. That is the part worth keeping: the command line tool is a projection of the class, not a second implementation of it.

There is more that jsonargparse can do with the same class, including shell completion, deeper trees of subcommands, and dependency injection through type hints. The [documentation](https://jsonargparse.readthedocs.io/) has the details.

## Disclosure, and the alternatives

I am the author of jsonargparse, so this post is a showcase of its features and you should read it with that in mind. The idea it rests on, that a command line interface can be derived from what the code already declares, is not mine and not exclusive to this package. Several others do a good part of it, and for a given project one of them may fit better. Here is what they do and where they stop, checked against click 8.4, typer 0.27, fire 0.7 and tyro 1.0.

[Fire](https://github.com/google/python-fire) is the closest in spirit. `fire.Fire(EarthquakeCatalog)` also turns constructor parameters into flags, methods into subcommands and docstrings into help. What it does not do is take the type hints seriously: `--days=notanumber` arrives at the method as that string, and `--area='{"latitude": 1, "longitude": 2}'` arrives as a plain `dict` rather than an `Area`. There is no config file support. Fire is built to expose arbitrary Python objects, not objects written to be exposed, so it guesses where jsonargparse validates.

[Tyro](https://github.com/brentyi/tyro) is the closest on types. It builds the parser from hints and docstrings, and its handling of nested structures is excellent: the same `area: Area | None` becomes a neat pair of `area:area` and `area:none` subcommands. It works from a function or a single class, though. `tyro.cli(EarthquakeCatalog)` gives you the constructor's options and returns an instance; the methods do not become subcommands. There is also no general `--config file.yaml`, only helpers to serialize dataclasses to and from YAML and to pick among configurations defined in code.

[Typer](https://github.com/fastapi/typer) derives options from the hints of functions registered with `@app.command()`. `Literal` becomes choices and `int` is validated, but past the simple types it stops: a dataclass parameter raises `RuntimeError: Type not yet supported`. Per-parameter help does not come from the docstring either, it is written again inside an `Annotated` hint with `typer.Option(help=...)`. In exchange you get click underneath, nicely formatted help and shell completion that installs itself with one flag.

[Click](https://github.com/pallets/click) is the established one and is explicit on purpose. Every option is a decorator, so nothing is inferred: a parameter with only a type hint produces no option at all, and the docstring becomes the description verbatim, `Args:` section and all. That explicitness is an advantage whenever the command line should not have the same shape as the Python API, and nothing matches click's ecosystem or its control over the terminal. It is a cost when the CLI is meant to be the API, which is the case in this post.

What jsonargparse adds here is the combination: a class with methods becomes a tree of subcommands, arbitrary type hints are validated rather than guessed, and the same tree can be filled from a config file or the environment instead of the command line. And `auto_cli` is only one way in. Underneath it is an argparse-like interface where you build the parser yourself and add arguments one at a time, or from a function, a class, a method or a bare type hint, wherever you want them, and link one to another. This post shows a small part of what is there.

None of which settles the question. For a tool the size of the one built here any of these packages does the job, and the differences that matter tend to surface later: when the interface grows to cover more of an API, when users start wanting their settings in a file, when the types stop being strings and integers. So the advice is the boring kind. Try a couple of them against the tool you expect to have in a year, rather than the one you are writing this afternoon.
