# Hideout Rebuild

A tracker for rebuilding your Escape from Tarkov hideout and trader levels after a prestige reset (PvE).

It is a single web page. Open `index.html`, or the hosted link, and it shows:

- **Build order**: which hideout upgrades you can build now, in a recommended order.
- **Shopping list**: every item still needed, with found-in-raid counts and flea prices.
- **Traders**: loyalty level requirements and each trader's opening tasks.
- **Prestige prep**: what resets, what carries over, and a suggested transfer grid.
- **Player tips**: task order, skill gates and the requirements for every prestige level.

Progress saves in your own browser. Nothing is uploaded.

## Syncing completed tasks from your game logs

On the Traders tab, "Choose Logs folder" reads the game's own log files and ticks off tasks the game recorded
as completed. The files are read in your browser only. Do not send your log files to anyone; they contain
account and network details.

## Keeping the data current

Hideout requirements, task lists and prices come from [tarkov.dev](https://tarkov.dev)'s public data.

```
python tools/refresh.py
```

This downloads current data, checks it, and rewrites `index.html`. If the download or the checks fail,
nothing is overwritten. It needs Python 3.9 or newer and no extra packages.

The GitHub Actions workflow in `.github/workflows/refresh.yml` runs the same script once a day and commits
the result, which updates the hosted page.

| Path | What it is |
|---|---|
| `index.html` | The built page. This is what gets served. |
| `src/template.html` | The page's layout and code. Edit this, then run the refresh. |
| `tools/refresh.py` | Downloads data and builds `index.html`. |
| `build/` | Downloads and outputs, not tracked. Includes a zip for sending to someone. |

## Credits

Game data from tarkov.dev. Prestige rules checked against the Escape from Tarkov Wiki.
Game content and materials are trademarks and copyrights of Battlestate Games.
