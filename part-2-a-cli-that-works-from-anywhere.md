# A CLI that works from anywhere

The [previous post](part-1-from-api-client-class-to-cli.md) turned a client class into a command line tool with a single call to `auto_cli`. It ended with a file you run like this:

```bash
python quakes_cli.py search --min_magnitude=5
```

That is fine while you are the only user and the terminal happens to be open in the right directory. It stops being fine as soon as it is not: the path has to be spelled out in full, `quakes_client.py` has to be next to it so the import works, and jsonargparse has to be installed in whichever Python `python` means today. A cron job or a colleague will run into all three.

What you want instead is a command:

```
$ cd ~
$ quakes count --start=2026-07-01 --min_magnitude=5
243
```

Available from any directory, with its dependencies installed along with it, and no mention of Python anywhere in the invocation. That takes one new file, `pyproject.toml`, and a small change to the code that already exists.

## The CLI needs a function

An installed command is a small script that the packaging tool generates and puts on your `PATH`. All it does is import something from your code and call it. So there has to be something to call, and a body sitting inside `if __name__ == "__main__"` is not it: that block runs when the file is executed as a script, and is skipped when the file is imported — and importing is exactly what the generated script does.

So the tail of `quakes_cli.py` goes from this:

```python
if __name__ == "__main__":
    try:
        print(render(auto_cli(EarthquakeCatalog)))
    except CatalogError as ex:
        sys.exit(f"error: {ex}")
```

to this:

```python
def main() -> None:
    """Run the command line interface."""
    try:
        print(render(auto_cli(EarthquakeCatalog)))
    except CatalogError as ex:
        sys.exit(f"error: {ex}")


if __name__ == "__main__":
    main()
```

The body did not change, only where it lives. The `if __name__` block stays, now one line long. Keeping it costs nothing, means the file is still runnable directly while developing, and keeps every command in the first post working as it was written.

The same applies to your own tools, whether or not you ever package them. Whatever is inside `if __name__ == "__main__"` should be one call to a function that lives just above it.

## pyproject.toml

One file declares what the project is, what it needs, and what it installs:

```toml
[build-system]
requires = ["setuptools>=77.0"]
build-backend = "setuptools.build_meta"

[project]
name = "quakes-cli"
version = "0.1.0"
description = "Command line client for the earthquake catalog of the U.S. Geological Survey."
requires-python = ">=3.10"
dependencies = [
    "jsonargparse[signatures]>=4.50.0",
]

[project.scripts]
quakes = "quakes_cli:main"

[tool.setuptools]
py-modules = ["quakes_cli", "quakes_client"]
```

That is the whole of it, minus the metadata that every published project also wants and that changes nothing in how any of this works: the readme, the license, the authors, the URLs. [The file in the repository](https://github.com/mauvilsa/blog-earthquake-cli/blob/main/pyproject.toml) has those as well.

`[build-system]` names the tool that turns this directory into something installable. Setuptools is the default choice and the one most people already have; hatchling, flit and pdm are equally valid and differ mostly in the last section of this file.

`[project]` is the metadata, standardised in [PEP 621](https://peps.python.org/pep-0621/) and identical whichever build backend you picked. The two lines doing real work are `dependencies` and `requires-python`. The former replaces `requirements.txt`, which the repository no longer has: what a package needs belongs in the package's own metadata, so that installing the package installs its dependencies too, in a fresh environment, on a machine that never saw this repository. The latter is what stops `pip` from installing this on Python 3.9, where the `float | None` hints that the client is written with fail on import.

`[project.scripts]` is the point of the exercise:

```toml
quakes = "quakes_cli:main"
```

On the left, the name the command has in a terminal. On the right, the function it calls, as `module:function`. The two are independent, so the command does not have to be named after the module, and one project can declare several commands pointing at different functions. This is also where the `main` of the previous section earns its existence.

`[tool.setuptools]` is the one backend-specific part. This project is two files at the root of the repository rather than a package directory, so they are declared as `py-modules`. That is unusual enough to explain: most projects put their code in a package, both to claim a single name in `site-packages` and to have somewhere to grow. Here, `quakes_cli` and `quakes_client` are specific enough not to collide with anything else installed, and leaving them where the first post put them keeps its snippets running. Adding a third module would be the moment to reconsider.

Three names show up in that file, which is a common source of confusion. `quakes-cli` is the distribution name, the one used to install and the one that has to be unique on PyPI. `quakes_cli` is the module. `quakes` is the command. They are allowed to differ, and often have to.

## Installing it

While working on the project, install it in editable mode:

```
$ pip install -e .
Building wheels for collected packages: quakes-cli
  Building editable for quakes-cli (pyproject.toml): finished with status 'done'
Successfully built quakes-cli
Installing collected packages: quakes-cli
Successfully installed quakes-cli-0.1.0
```

The sources stay where they are and the environment points at them, so an edit takes effect on the next run with nothing to reinstall. Drop the `-e` and it copies instead, which is what you want when checking that the install itself is correct.

Either way there is now a `quakes` on the `PATH`, and it behaves like any other command:

```
$ cd ~
$ quakes --help
usage: quakes [--config CONFIG] [--distance_unit {km,mi}]
              [--min_magnitude MIN_MAGNITUDE] [--timeout TIMEOUT]
              {count,event,feed,search,summary} ...
```

Note the usage line. It said `quakes_cli.py` before and says `quakes` now, and nothing was configured to make that happen: argparse takes the program name from how the program was invoked, so the help follows the command around.

For people who only want to use the tool, `pipx install .` or `uv tool install .` are the friendlier form; once the project is published somewhere, the dot becomes the distribution name. Both put the command on the `PATH` and keep its dependencies in an environment of their own, so a CLI never has to share an environment with anything else.

## Settings that follow the command

Something did not survive the move. The first post ended with the client's settings in a config file:

```bash
quakes --config config.yaml search --start=2026-07-01
```

That path is resolved relative to the directory you are standing in, which used to be the repository and can now be anywhere. A command that runs from everywhere, but whose settings only work in one directory, is not much of an improvement.

The fix is one argument. Anything `auto_cli` does not recognise is handed to the parser, and the parser accepts a list of places to read configuration from on every run, without `--config` having to point at them:

```python
auto_cli(
    EarthquakeCatalog,
    default_config_files=["~/.config/quakes.yaml"],
)
```

Write the settings there once:

```yaml
# ~/.config/quakes.yaml
distance_unit: mi
min_magnitude: 4.0
```

and they apply from every directory, with nothing on the command line:

```
$ cd ~
$ quakes count --start=2026-08-01
113
```

The file gives defaults, not final values, so `--config` still overrides it, and a command line argument overrides both:

```
$ quakes --min_magnitude=6 count --start=2026-08-01
2
```

The help says what is going on, at the top and in the defaults of every option the file touched:

```
$ quakes --help
usage: quakes [--config CONFIG] [--distance_unit {km,mi}]
              [--min_magnitude MIN_MAGNITUDE] [--timeout TIMEOUT]
              {count,event,feed,search,summary} ...

default config file locations:
  ['~/.config/quakes.yaml'], Note: default values below are the ones
  overridden by the contents of: ~/.config/quakes.yaml
...
  --distance_unit {km,mi}
                        Unit used for all distances, both given and returned.
                        (type: Literal['km', 'mi'], default: mi)
```

`default: mi` is not what the client's signature says, because the file said otherwise. `--help` reports what a run would actually use, not what the code was written with.

The entries are glob patterns and more than one is allowed, with later files winning over earlier ones. So the layering that well behaved command line tools tend to have costs one keyword argument:

```python
default_config_files=["/etc/quakes.yaml", "~/.config/quakes.yaml", "quakes.yaml"]
```

A system wide file, then the user's, then one for the project you happen to be standing in. That first path is the Unix convention and has no Windows equivalent. `~/.config` does work on Windows, but no user there expects to find settings in it; if you would rather use each operating system's native location, [platformdirs](https://pypi.org/project/platformdirs/) computes it, and `default_config_files` takes `Path` objects as readily as strings.

## What this leaves you with

The tool is now something that can be installed rather than a file that can be run. It declares its own dependencies, refuses to install where it would not work, gives its user a command instead of a path, carries its settings around, and can be built into a wheel and put on PyPI or an internal index with `python -m build` and `twine upload`.

The part that carries beyond this project is the smallest one. An entry point needs a function, so write the function and let `if __name__ == "__main__"` do nothing but call it.
