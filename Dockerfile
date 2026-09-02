# Image for the quakes command, used by part 4 to show the settings arriving
# through the environment rather than through a file.
FROM python:3.12-slim

WORKDIR /src
COPY pyproject.toml README.md LICENSE quakes_cli.py quakes_client.py ./
RUN pip install --no-cache-dir .

# No arguments. Everything the run needs is passed with -e, including which
# subcommand to run.
ENTRYPOINT ["quakes"]
