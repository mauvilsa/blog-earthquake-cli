# Tab completion, without writing a completion script

The [first post](part-1-from-api-client-class-to-cli.md) derived a whole command line interface from a client class, and the [second](part-2-a-cli-that-works-from-anywhere.md) turned it into a command that runs from any directory. Both left the same gap in place: the tool knows a great deal that its user does not.

`order_by` is one of four strings. `distance_unit` is one of two. `level` is one of five. The client says so in its type hints, and jsonargparse enforces every one of them, to the point of refusing the run when you get it wrong:

```
$ quakes search --order_by=depth
error: Parser key "order_by":
  Expected a typing.Literal['time', 'time-asc', 'magnitude', 'magnitude-asc']. Got value: depth
```

Which is correct, and arrives too late to be of much use. The alternatives on offer are to remember the four values or to stop and read `quakes search --help`. Neither is what you want at forty characters into a command line.

Tab completion is where that knowledge belongs, and there is nothing to invent for it. The parser has the choices. The shell has a mechanism for asking. All that is missing is the translation between the two, and it is one dependency and one line of code away.

## The part that is normally the work

A shell completion is a script in the shell's own language, registered against a command name. Writing one by hand is a small, unpleasant project: bash wants a function that fills `COMPREPLY`, zsh wants `_arguments` specs in a file whose first line is `#compdef`, fish wants a pile of `complete -c` calls, tcsh wants a single `complete` statement built out of `c/`, `n/` and `p/` patterns. Four dialects, none of which resemble the others.

Worse than writing them once is keeping them. The completion script is a copy of the interface expressed somewhere else, and it goes stale the moment you add an option and forget. Plenty of tools ship a completion that is a version or two behind what the tool accepts.

None of that is necessary when the parser can be inspected. [shtab](https://github.com/iterative/shtab) walks an `argparse` parser and writes the script for you, and jsonargparse hands it a parser that already knows the choices, the paths and the types, because those came out of the client's signatures. So the completion ends up derived from the same source as everything else in this series.

## One extra, one line

shtab is an optional dependency of jsonargparse, declared as the `shtab` extra. In [pyproject.toml](pyproject.toml) it goes next to the extra that was already there:

```toml
dependencies = [
    "jsonargparse[signatures,shtab]>=4.51.0",
]
```

```bash
pip install -e .
```

Installing shtab is enough for the machinery to exist, but not for the command to expose it. The argument that prints the script is opt-in, because not every program wants an extra option in its help. Turning it on is a module level call in [quakes_cli.py](quakes_cli.py), next to the `register_type` from part 1:

```python
from jsonargparse import auto_cli, set_parsing_settings

# Add --print_completion, which writes the shell completion script for the CLI.
set_parsing_settings(add_print_completion_argument=True)
```

`set_parsing_settings` is jsonargparse's dial for behaviours that apply to every parser in the process rather than to one argument. There is now one more option in the help:

```
$ quakes --help
options:
  -h, --help            Show this help message and exit.
  --config CONFIG       Path to a configuration file.
  --print_config [=flags]
                        Print the configuration after applying all other
                        arguments and exit. ...
  --print_completion {shtab-bash,shtab-zsh,shtab-tcsh,shtab-fish}
                        Print shell completion script.
```

Note what did not happen. [quakes_client.py](quakes_client.py) was not touched, no argument was annotated with a completer, and nothing anywhere said that `order_by` has four values. That was said once, in the client's signature, and this is the third thing generated from it after the parser and the help.

If the tool is not yours to edit, the same argument can be added from outside with an environment variable:

```bash
JSONARGPARSE_ADD_PRINT_COMPLETION_ARGUMENT=true some-other-tool --print_completion=shtab-bash
```

## Trying it in bash

`--print_completion` writes a script to standard output and exits. To try it in the shell you are sitting in, run it and evaluate the result:

```bash
eval "$(quakes --print_completion shtab-bash)"
```

That lasts until the shell closes, which is what you want while deciding whether any of this is worth keeping. Subcommands complete:

```
$ quakes <TAB><TAB>
count    event    feed     search   summary
$ quakes su<TAB>
$ quakes summary
```

A single dash is enough to ask for options, and which options you are offered depends on where you are. Before a subcommand, the ones that configure the client, which is exactly the set that part 1 got out of `__init__`:

```
$ quakes -<TAB><TAB>
--config         --help           --print_config   -h
--distance_unit  --min_magnitude  --timeout
```

After a subcommand, that subcommand's own, which is the set that came out of the method. `--order_by` and `--limit` belong to `search` and are not offered under `count`:

```
$ quakes search --<TAB><TAB>
--area            --area.longitude  --end             --max_magnitude   --print_config
--area.help       --area.radius     --help            --min_magnitude   --start
--area.latitude   --config          --limit           --order_by

$ quakes count --<TAB><TAB>
--area            --area.longitude  --end             --min_magnitude
--area.help       --area.radius     --help            --print_config
--area.latitude   --config          --max_magnitude   --start
```

That split is not something shtab was told about. It falls out of the parser having a subparser per method, which fell out of the client having a method per subcommand.

And values complete, which is the part that pays for the exercise:

```
$ quakes search --order_by <TAB><TAB>
Expected type: Literal['time', 'time-asc', 'magnitude', 'magnitude-asc']; 4/4 matched choices
magnitude      magnitude-asc  time           time-asc
$ quakes search --order_by m<TAB>
$ quakes search --order_by magnitude
```

The line above the choices is jsonargparse rather than shtab, and it is the reason a generated completion can end up better than a hand written one. Pressing tab twice asks the shell to list what it has; jsonargparse takes the chance to also print the declared type and how much of it your prefix still matches, in colour, on standard error, without disturbing the line you are typing. For an argument with choices that is a convenience. For one without, it is the whole answer:

```
$ quakes search --limit <TAB><TAB>
Expected type: int

$ quakes search --start <TAB><TAB>
Expected type: date | null; 0/1 matched choices
```

`--start` is the `date` that part 1 taught the parser with `register_type`. There is no list of dates to offer, so the type is what gets shown, and the `1` counts the one value it can complete, the `null` that the type names.

Arguments whose type is a path complete as paths, because shtab is told so from the type rather than from a hint written by hand. `--config` is the clearest case, since the client does not declare it at all:

```
$ quakes --config <TAB><TAB>
config.yaml  config_japan.yaml  data/
```

The most interesting type in the client goes one level deeper. `area` is the `Area` dataclass behind an `Area | None` hint, and part 1 set its fields from the command line as `--area.latitude` and friends. Those complete too, dot and all:

```
$ quakes search --area.<TAB><TAB>
--area.help       --area.latitude   --area.longitude  --area.radius

$ quakes search --area.latitude <TAB><TAB>
Expected type: float
```

Nothing about the nesting was declared anywhere either. Three annotated fields on the dataclass become three more options on the parser, and three more candidates in the completion, each carrying its own type. `--area.help` is in that list because it is a real option, the one part 1 used to print the dataclass's own help page.

## Making it stick

Typing the `eval` by hand is fine for an afternoon. The question is where to put it so that it is simply there.

The tempting answer is to generate the script once, save it, and source the file. For a project you are working on, that is the wrong shape. The install is editable; the whole point of it is that the code changes under a command that stays where it is. A completion script written at setup time starts drifting from the interface on the second afternoon, and drifting quietly, which is the failure mode that made hand written completions unpleasant in the first place.

So keep the `eval` and move it somewhere that runs. In a virtual environment the natural place follows from what a virtual environment is: activating it is the moment `quakes` appears on the `PATH`, and that is the moment the shell should learn how to complete it. `activate` is a plain script that gets sourced, so appending to it is all it takes:

```bash
cat >> "$VIRTUAL_ENV/bin/activate" <<'EOF'

# Shell completion for the quakes command.
eval "$(quakes --print_completion shtab-bash)"
EOF
```

From then on the completion is regenerated from the current code every time you activate, and there is nothing to keep in sync:

```
$ source venv/bin/activate
(venv) $ quakes search --order_by <TAB><TAB>
Expected type: Literal['time', 'time-asc', 'magnitude', 'magnitude-asc']; 4/4 matched choices
magnitude      magnitude-asc  time           time-asc
```

Two things this does not do. `deactivate` does not undo it, so the completion stays registered for the rest of the session; harmless, since it only fires for a command that is no longer on the `PATH`. And `python -m venv` writes `activate` fresh, so recreating the environment loses the appended block. Worth keeping the `cat >>` above in a script you rerun rather than in your shell history.

For a tool you installed rather than one you are writing, the same line goes in `~/.bashrc` instead, and the reasoning is unchanged: the completion is generated from whatever version is installed today.

## Or a file, when the startup cost matters

There is a cost to the above, and it is the one thing a saved script buys back. Every `eval` starts a Python interpreter, imports jsonargparse, builds the parser out of the client's signatures and walks it. Here that is about a quarter of a second:

```
$ time quakes --print_completion shtab-bash > /dev/null
real	0m0.276s
user	0m0.223s
sys	0m0.042s
```

Once per `source venv/bin/activate` is nothing. Once per terminal you open is noticeable, and it is not once: put four tools in your `~/.bashrc` this way and you have added a second to every shell. That is the point at which to generate the file instead and let the shell load it, which is also the right thing for a tool other people install, since they gain nothing from paying for a generation step on a program that only changes when they upgrade it.

Each shell has a directory for exactly this. bash looks in `/etc/bash_completion.d/` and, with the [bash-completion](https://github.com/scop/bash-completion) package, in `~/.local/share/bash-completion/completions/`, under the command's name:

```bash
quakes --print_completion shtab-bash > ~/.local/share/bash-completion/completions/quakes
```

zsh loads from any directory on `$fpath`, from a file named `_quakes` whose first line is `#compdef quakes`, which is what shtab writes:

```bash
quakes --print_completion shtab-zsh > /usr/local/share/zsh/site-functions/_quakes
```

fish reads `~/.config/fish/completions/quakes.fish`, and needs no configuration line anywhere:

```bash
quakes --print_completion shtab-fish > ~/.config/fish/completions/quakes.fish
```

tcsh has no such directory; the file goes wherever you like and `~/.tcshrc` sources it.

The trade is the obvious one. Nothing is generated at startup, and nothing notices when the interface changes, so the generation has to happen somewhere else: an installer step, a `make` target, whatever the project already runs. That is the same discipline a hand written completion needs, minus the writing.

One detail to watch either way. The script registers itself against the program name the parser saw, so running `python quakes_cli.py --print_completion shtab-bash` ends the script with `complete -o filenames -F _shtab_quakes_cli_py quakes_cli.py`, which completes a file path rather than a command. Generate from the installed command, so that the name in the script is the name people type.

## The other three shells

Everything above is `shtab-bash`. The other values of `--print_completion` produce scripts in the other shells' languages, out of the same parser, and the differences between them are the shells' own.

A caveat before the details: bash is the shell I actually use. Everything below was run and its output is real, but it was run by someone who had to look up the syntax first, so take the surrounding judgements as a starting point rather than as advice from a native. If your shell is one of these three and something here is not how it is done, you are right and I am not.

**zsh** gives the most back. It shows the help text next to each candidate, because the parser had it and zsh has somewhere to put it:

```
% quakes <TAB>
count    -- Count the events matching the given criteria, without fetching them.
event    -- Get everything the catalog knows about a single event.
feed     -- Get one of the real time feeds of recent events.
search   -- Search the catalog for events matching the given criteria.
summary  -- Summarize the seismic activity of a period as aggregated statistics.
```

Those sentences are the first lines of the docstrings in the client, which have now been through the help, the completion and nowhere else. Options are scoped to the subcommand as they are in bash, and values complete the same way, without the type guidance, which is a bash-only addition.

The one wrinkle is that zsh does not register a completion by being told the function exists. Its convention is the `#compdef` file on `$fpath` from the previous section, read by `compinit` at startup; anything arriving later has to be attached by hand. So the `eval` needs a second line:

```bash
eval "$(quakes --print_completion shtab-zsh)"
compdef _shtab_quakes quakes
```

`activate` is the same file for bash and zsh, so if you use both, branch on `$BASH_VERSION` and `$ZSH_VERSION`:

```bash
# Shell completion for the quakes command.
if [ -n "$BASH_VERSION" ]; then
    eval "$(quakes --print_completion shtab-bash)"
elif [ -n "$ZSH_VERSION" ]; then
    eval "$(quakes --print_completion shtab-zsh)"
    compdef _shtab_quakes quakes
fi
```

**fish** also shows descriptions, and asks the least of the four:

```
> quakes <TAB>
count    (Count the events matching the given criteria, without fetching them.)
event    (Get everything the catalog knows about a single event.)
feed     (Get one of the real time feeds of recent events.)
search   (Search the catalog for events matching the given criteria.)
summary  (Summarize the seismic activity of a period as aggregated statistics.)

> quakes search --m<TAB>
--max_magnitude  (Only events at or below this magnitude. (type: float | null,…)
--min_magnitude  (Only events at or above this magnitude. Defaults to the valu…)
```

fish has no `eval`, and does not need one: a script can be piped straight into `source`. That line goes in `activate.fish`, which is the file fish reads:

```fish
# Shell completion for the quakes command.
quakes --print_completion shtab-fish | source
```

**tcsh** is the modest one, and the only one where the generated script is worse than the shell can do. Its completions are a single `complete` statement, and shtab writes it with the options of every subparser merged into one list, so `--level`, which belongs to `feed` alone, is offered everywhere:

```
> quakes <TAB>
count   event   feed    search  summary
> quakes search --order_by <TAB>
magnitude     magnitude-asc time          time-asc
> quakes count --level <TAB>
1.0         2.5         4.5         all         significant
```

That flattening is shtab's, not tcsh's. tcsh completions can run a command to produce their candidates, and that command can look at `$COMMAND_LINE` and answer differently depending on the subcommand already typed; shtab uses exactly this technique for positional arguments and simply does not for options. It is also worth knowing that a single dash offers `-` and `h` rather than the long options, so `--` is what you want to type before pressing tab. Both are fixable in shtab rather than facts about the shell.

For the rest, tcsh does what the others do. The only awkwardness is getting the script in without a file: csh's backticks flatten the multi-line `complete` statement, so the comment lines and the line continuations have to go before `eval` sees it. In `activate.csh`:

```csh
# Shell completion for the quakes command.
eval `quakes --print_completion shtab-tcsh | grep -v '^#' | tr -d '\\'`
```

Which is a coincidence worth pointing out. `python -m venv` writes `activate`, `activate.csh` and `activate.fish`; shtab writes bash, zsh, tcsh and fish. The shells Python thinks are worth an activation script are the shells shtab can complete.

## The one thing to remember

Whatever you do with it, the script is a snapshot. It is written from the parser at the moment `--print_completion` ran, and it does not change afterwards. Add a parameter to `EarthquakeCatalog` and the CLI grows an option immediately, because the class is read on every run, while a completion generated yesterday keeps offering yesterday's list.

Which is why the shape of the question is *when do I regenerate*, not *where do I keep the file*. Every activation, and you never think about it again for the price of a quarter of a second. Every install, and it is correct for as long as the version is. Once, by hand, in a terminal you have since closed, and it will be wrong and you will not be told.

## What this leaves you with

Three posts in, the client class has produced the argument parser, the help, the keys a config file may set and now the completions for four shells, and it still does not import jsonargparse. The pattern is the same every time: write the interface honestly in Python, and the things that are usually hand maintained copies of it stop being copies.

Completion is the clearest case of it, because a hand written one is so plainly a duplicate of something you already wrote down. Whatever library you use, if it can walk your parser, generating the script is worth the afternoon you would otherwise spend writing one that is wrong by next month.
