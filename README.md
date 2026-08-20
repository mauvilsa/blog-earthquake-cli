# A command line tool for the earthquake catalog

A small client for the [USGS Earthquake Catalog](https://earthquake.usgs.gov/fdsnws/event/1/), and the command line tool that [jsonargparse](https://github.com/mauvilsa/jsonargparse) derives from it. The catalog needs no key and no account, so everything here runs against real data as it is written.

```bash
pip install .
quakes search --min_magnitude=6 --limit=5
```

The code is the subject of a series of posts, each one a step further from the class:

- [Part 1: From API client to CLI, without writing a parser](part-1-from-api-client-class-to-cli.md) — building the client, and getting the whole command line interface out of its signatures and docstrings with one call to `auto_cli`.
- [Part 2: A CLI that works from anywhere](part-2-a-cli-that-works-from-anywhere.md) — making the project pip installable, so that `quakes` runs from any directory, and giving it a config file it finds on its own.
- [Part 3: Tab completion, without writing a completion script](part-3-tab-completion.md) — generating shell completions for bash, zsh, tcsh and fish out of the same type hints, and wiring them into the virtual environment.

The repository holds the finished version, so it is ahead of the earlier posts. `quakes_client.py` is the client, plain Python that knows nothing about command lines. `quakes_cli.py` is the interface.
