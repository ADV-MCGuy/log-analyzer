# log-analyzer
Analyze system logs for error patterns, frequency metrics, and trend analysis.

Runs fully offline. Python 3.8+ standard library only (SQLite is built in).

## Usage

Run straight from a checkout:

```
./logan ingest /path/to/app.log [more.log ...]   # parse into ./logan.db
./logan summary                                  # levels, top errors/warnings, errors by component
./logan summary --source 2 --top 10              # just one file
./logan sources                                  # list ingested files
./logan remove 2                                 # drop a file and its entries
```

Or install it so `logan` is on your PATH: `pip install --no-build-isolation .`
(`--no-build-isolation` uses the local setuptools so pip doesn't try to download it).

- `--db PATH` (or `LOGAN_DB=PATH`) picks the database file; default is `./logan.db`.
- Ingesting the same file twice (same path or identical contents) is skipped, so counts
  aren't doubled. Use `ingest --replace` to re-ingest a file that has changed.
- The log format has no year, so `ingest --year` sets the year of the first entry
  (default: current year). Logs that cross New Year are handled.
- `ingest -v` shows lines that couldn't be parsed.

## Supported format

```
DD Mon HH:MM:SS [LEVEL] Component | Message
07 Sep 14:27:29 [INFO] Laser Range Finder | Sent command to stop laser range finder
```

## Tests

```
python3 -m unittest discover -s tests
```
