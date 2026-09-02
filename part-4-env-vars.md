# Settings from the environment

The [second post](part-2-a-cli-that-works-from-anywhere.md) gave the tool a config file it finds on its own, so that `~/.config/quakes.yaml` decides what `quakes` does from any directory. That solves the problem for a person with a home directory, and it is the right default for one. It also assumes a filesystem you can write to before the program runs, which is the assumption that fails everywhere else the command is likely to end up.

A container image is built once and run with different settings. A CI job gets its configuration from the thing that started it. A systemd unit has `Environment=` lines and no obvious place to put a YAML file. In all three the settings arrive as environment variables, because that is the one channel a process always has, and the usual response is a block of `os.environ.get` calls somewhere near the top of the program, with its own names, its own defaults and its own idea of how to turn `"6"` into a float.

That block is another copy of the interface, in the same way the completion script in [part 3](part-3-tab-completion.md) was a copy. The parser already knows every setting the program has, what type each one is and what it defaults to. Reading them from the environment instead of from `argv` is a different source for the same values, and it is two keyword arguments.

## Two arguments, again

The change is in [quakes_cli.py](quakes_cli.py), next to the one from part 2:

```python
result = auto_cli(
    EarthquakeCatalog,
    # Settings written here apply from any directory, without --config.
    default_config_files=["~/.config/quakes.yaml"],
    # And these let a process pass settings in without a file at all.
    # The prefix is spelled out because prog changes when the module is
    # run directly, and the variable names should not change with it.
    env_prefix="QUAKES",
    default_env=True,
)
```

`default_env=True` is what turns the parsing on. `env_prefix` is the first part of every variable name, and it is worth being explicit about even here, where the value looks redundant. Left unset, the prefix is derived from the program name, which is `quakes` when the installed command runs and `quakes_cli.py` when the module is run directly, as [part 1](part-1-from-api-client-class-to-cli.md) still does. Deriving it would mean `QUAKES_MIN_MAGNITUDE` and `QUAKES_CLI_MIN_MAGNITUDE` naming the same setting depending on how the program was started. Writing the prefix down costs one line and removes that.

## The names are already decided

The rule is `PREFIX_`, then the argument name in upper case, with each dot replaced by two underscores. Client options are one level deep, so `--min_magnitude` is `QUAKES_MIN_MAGNITUDE`. A subcommand's options are two, so `search`'s `--limit` is `QUAKES_SEARCH__LIMIT`.

Which is a rule nobody should have to remember, and does not have to, because the help now prints the variable next to the option it sets:

```
$ quakes --help
options:
  ARG:   -h, --help     Show this help message and exit.
  ARG:   --config CONFIG
  ENV:   QUAKES_CONFIG
                        Path to a configuration file.
...
Client for the earthquake catalog of the U.S. Geological Survey:
  ARG:   --distance_unit {km,mi}
  ENV:   QUAKES_DISTANCE_UNIT
                        Unit used for all distances, both given and returned.
                        (type: Literal['km', 'mi'], default: km)
  ARG:   --min_magnitude MIN_MAGNITUDE
  ENV:   QUAKES_MIN_MAGNITUDE
                        Magnitude below which events are ignored by default.
                        (type: float, default: 2.5)
```

The `ARG:` and `ENV:` labels appear only once environment parsing is on; before that the help looks as it did in the earlier posts. This is the part that tends to be missing when the variables are read by hand. A program with fifteen `os.environ.get` calls has fifteen names documented in a README if you are lucky, and the README is where they go out of date. Here the list cannot drift, for the same reason the completions could not: it is printed from the parser, and the parser was built from the client's signature.

The same holds one level down, including for the positional:

```
$ quakes event --help
  ARG:   event_id
  ENV:   QUAKES_EVENT__EVENT_ID
                        Identifier of the event, e.g. ``us7000srb1``.
                        (required, type: str)
```

So a run of the tool can be assembled entirely out of the environment:

```
$ QUAKES_MIN_MAGNITUDE=6 quakes count --start=2026-07-01
13
$ quakes --min_magnitude=6 count --start=2026-07-01
13
```

## The subcommand is a variable too

Note the name in the help for the subcommands group:

```
$ quakes --help
subcommands:
  ENV:   QUAKES_SUBCOMMAND
```

The choice of subcommand is an argument like the others, so it is available the same way, and with it the command line can be empty. That is exactly the shape a container wants, and it is what makes the whole [Dockerfile](Dockerfile) this:

```dockerfile
FROM python:3.12-slim

WORKDIR /src
COPY pyproject.toml README.md LICENSE quakes_cli.py quakes_client.py ./
RUN pip install --no-cache-dir .

# No arguments. Everything the run needs is passed with -e, including which
# subcommand to run.
ENTRYPOINT ["quakes"]
```

No `CMD`, and nothing in the image that says what it does when it starts. Build it once:

```bash
docker build -t quakes .
```

A real image is named `{registry}/{project}/quakes-cli:{tag}`, and the short name is only used here to keep the runs below down to the part that matters. It does mean the image is spelled exactly like the command, so in every `docker run` that follows, the bare `quakes` on the last line is the image and anything after it is what gets appended to the entry point.

With that, the run is described entirely by its environment:

```
$ docker run --rm \
    -e QUAKES_SUBCOMMAND=count \
    -e QUAKES_COUNT__MIN_MAGNITUDE=6 \
    -e QUAKES_COUNT__START=2026-07-01 \
    quakes
13
```

There is no home directory in that container, therefore no `~/.config/quakes.yaml`, therefore nothing but what was handed in. The same image and the same entry point, with a different set of variables, give a different program:

```
$ docker run --rm \
    -e QUAKES_SUBCOMMAND=search \
    -e QUAKES_DISTANCE_UNIT=mi \
    -e QUAKES_SEARCH__MIN_MAGNITUDE=6.5 \
    -e QUAKES_SEARCH__START=2026-07-01 \
    -e QUAKES_SEARCH__LIMIT=3 \
    quakes
time              magnitude  depth  latitude  longitude  id          place
2026-07-28 07:27  6.8        6.21   32.6817   130.7217   us6000tgb9  The 2026 Kumamoto Region, Japan Earthquake
2026-07-17 14:48  7.3        13.67  14.6361   -92.8969   us7000t1bu  52 km W of Puerto Madero, Mexico
```

Dates arrived as dates and `mi` reached the client, because `register_type(date, ...)` and the `Literal` from part 1 apply here too. The environment is a different source, not a different type system.

None of this closes the command line off. An `ENTRYPOINT` with no `CMD` appends whatever you put after the image name, so the same image is still the tool it was:

```
$ docker run --rm quakes count --min_magnitude=6 --start=2026-07-01
13
```

Which is the property worth protecting when a program grows a container. One image, driven by variables in production and by arguments when you are trying to work out what it did, with a single description of the settings behind both. A `.gitlab-ci.yml`, a Kubernetes `env:` block and a systemd unit's `Environment=` lines all reduce to the same thing.

## Where this sits in the order

There are now five places a value can come from, and the order between them is fixed:

1. The default in the client's signature.
2. The files in `default_config_files`, in the order given.
3. The config file named by `QUAKES_CONFIG`.
4. The individual variables, `QUAKES_MIN_MAGNITUDE` and friends.
5. The command line, left to right.

With part 2's file in place:

```yaml
# ~/.config/quakes.yaml
distance_unit: mi
min_magnitude: 4.0
```

each layer overrides the one before it:

```
$ quakes count --start=2026-07-01
1486
$ QUAKES_MIN_MAGNITUDE=6 quakes count --start=2026-07-01
13
$ QUAKES_MIN_MAGNITUDE=6 quakes --min_magnitude=7 count --start=2026-07-01
1
```

The ordering is the one that makes deployment work: the file is what the machine believes, the environment is what this run believes, the command line is what you believe right now. A container inherits the image's defaults and overrides the two settings the job cares about, without a file being rewritten anywhere.

`QUAKES_CONFIG` deserves its own line in that list. It takes a path and loads a whole file, which is the answer when a run needs more than a couple of settings changed, and it sits *below* the individual variables rather than above:

```yaml
# ci.yaml
distance_unit: mi
min_magnitude: 5.0
```

```
$ QUAKES_CONFIG=ci.yaml quakes count --start=2026-07-01
262
$ QUAKES_CONFIG=ci.yaml QUAKES_MIN_MAGNITUDE=6 quakes count --start=2026-07-01
13
```

Which is the combination a deployment usually ends up wanting, and in a container it is literally that: mount the file, name it with a variable, override the one setting this run disagrees about.

```
$ docker run --rm -v "$PWD/ci.yaml:/etc/quakes.yaml:ro" \
    -e QUAKES_CONFIG=/etc/quakes.yaml \
    -e QUAKES_SUBCOMMAND=count -e QUAKES_COUNT__START=2026-07-01 \
    quakes
262
$ docker run --rm -v "$PWD/ci.yaml:/etc/quakes.yaml:ro" \
    -e QUAKES_CONFIG=/etc/quakes.yaml -e QUAKES_MIN_MAGNITUDE=6 \
    -e QUAKES_SUBCOMMAND=count -e QUAKES_COUNT__START=2026-07-01 \
    quakes
13
```

Passing `--config /etc/quakes.yaml` after the image name works too, and puts the file above the variables instead. A third option is to bake the file into the image and name it in `default_config_files`, which makes it the image's defaults rather than the run's.

When the layers stop being obvious, `--print_config` from part 2 answers the question, and it answers it after the environment has been read:

```
$ QUAKES_SUBCOMMAND=count QUAKES_MIN_MAGNITUDE=6 quakes --print_config
distance_unit: mi
min_magnitude: 6.0
timeout: 30.0
count:
  start: null
  ...
```

That is the debugging tool worth knowing about before you need it. "Which of these four things won" is the whole difficulty of layered configuration, and the command prints the answer rather than requiring you to reconstruct it.

## Nothing is trusted more for arriving this way

Values from the environment go through the same validation as everything else, which is not the usual behaviour of a hand written `os.environ.get`, where the string reaches the code as a string and fails later, somewhere less helpful:

```
$ docker run --rm -e QUAKES_SUBCOMMAND=count -e QUAKES_DISTANCE_UNIT=miles quakes
error: Parser key "distance_unit":
  Expected a typing.Literal['km', 'mi']. Got value: miles
$ echo $?
2
```

The same `Literal` that produced the choices in the help in part 1 and the completions in part 3 rejects the value here, and it does so before the client is constructed. In a container that matters more than at a terminal. A typo in a deployment manifest is something you find out about from logs, and the difference between the container exiting immediately with that message and the program failing an hour later inside a request is most of the debugging. A non-zero exit at startup is also what a scheduler understands: the pod fails, it does not sit there serving errors.

## Where the environment stops

Three limits, all worth knowing before you build a deployment on this.

**A misspelled variable is silence.** `--min_mag=6` on the command line is an error, because the parser knows the option does not exist. `QUAKES_MIN_MAG=6` is not, because a process's environment is full of variables that are none of the program's business and it cannot tell yours from the rest:

```
$ QUAKES_MIN_MAG=6 quakes --print_config count
distance_unit: mi
min_magnitude: 4.0
```

The run proceeds with the file's value and no complaint. This is inherent to the mechanism rather than particular to jsonargparse, and `--print_config` is the check: if the value you set is not in the output, the name is wrong.

**An empty variable is a value, not an absence.** `QUAKES_MIN_MAGNITUDE=` sets it to the empty string, which fails to parse as a float:

```
$ QUAKES_MIN_MAGNITUDE= quakes count
error: Parser key "min_magnitude":
  Expected a <class 'float'>. Got value:
```

Shell scripts and CI templates produce empty variables easily, from an unset substitution or a job input nobody filled in. Unset the variable rather than blanking it.

**A structured value is one variable, not several.** `--area` is the `Area` dataclass from part 1, and on the command line it takes either a JSON document or its fields as separate options, `--area.latitude=35.7`. Through the environment only the first of those exists: the help lists `QUAKES_SEARCH__AREA` and nothing for `latitude`, so the entire dataclass arrives in one variable.

```
$ QUAKES_SEARCH__AREA='{"latitude": 35.7, "longitude": 139.7}' quakes search --limit=2
time              magnitude  depth   latitude  longitude  id          place
2026-08-20 05:28  4.3        29.68   36.651    140.6399   us6000tm2a  5 km N of Hitachi, Japan
2026-08-17 07:36  4.6        230.19  34.8761   135.6311   usd0015ecj  3 km NNE of Takatsuki, Japan
```

It is parsed and checked like every other value — leave out `longitude` and the run stops at startup saying so, rather than the dataclass being built without it. What does not improve is the writing: a JSON document squeezed into a shell variable is unpleasant to quote and hard to read in a manifest, and it gets worse the deeper the structure goes. Structure belongs in a config file, and `QUAKES_CONFIG` exists so that a run can point at one. Environment variables are for the handful of scalars that differ between runs.

## Leaving it off

`default_env=True` is a decision, and the opposite one is defensible. It means the program's behaviour depends on variables that a user cannot see in the command they typed, which is a real cost when someone is debugging over a shoulder, and prefixed names collide with nothing but are still a namespace claimed in every shell the command runs in.

If the tool is mostly used interactively, leave the argument out and let whoever needs it turn it on for a single run:

```bash
JSONARGPARSE_DEFAULT_ENV=true quakes count
```

Same mechanism as the `JSONARGPARSE_ADD_PRINT_COMPLETION_ARGUMENT` in part 3, and the same reasoning: a behaviour the program's author might not want on by default is still available to the person running it, without a fork. Keeping `env_prefix` set while leaving `default_env` unset is a reasonable middle, since it fixes the names for whoever does enable it.

One thing this post has not needed is a secret, because the earthquake catalog wants neither a key nor an account, which is why it makes such a convenient example. If it did want one, this is the mechanism it would arrive by, and the reason is the one part 2 gave for the config file: a token in a variable does not go into your shell history and does not get committed. What it does do is stay readable for as long as the container exists:

```
$ docker inspect --format '{{json .Config.Env}}' "$container"
["QUAKES_MIN_MAGNITUDE=6","QUAKES_SUBCOMMAND=count","PATH=...","LANG=C.UTF-8",...]
```

Anyone who can talk to the daemon can read that, and the same is true of `ps` on some systems and of whatever your CI prints when it dumps the environment for a failed job. A file with restrictive permissions, or a secret mounted as one, is still the better place for a long lived credential — `QUAKES_CONFIG` pointing at a mounted file is exactly that shape. The variable is the better place for a token that lives as long as the process does.

## What this leaves you with

The command now takes its settings from a file it finds on its own, a file named by a variable, individual variables, or the command line, and the same class decides what all four of them accept. Adding a parameter to `EarthquakeCatalog` still adds an option, a config key, a completion and, now, an environment variable, and [quakes_client.py](quakes_client.py) still does not import jsonargparse.

That is four posts of the same trade. Everything a command line tool conventionally maintains by hand — the parser, the help, the config schema, the completion script, the environment variable table — is a projection of something already written down in Python. Write it down accurately once, and the copies stop being copies.
