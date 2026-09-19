# QGIS mailing list explorer

An interactive view of twenty years of the QGIS mailing lists —
[qgis-developer](https://lists.osgeo.org/pipermail/qgis-developer/),
[qgis-user](https://lists.osgeo.org/pipermail/qgis-user/) and
[qgis-psc](https://lists.osgeo.org/pipermail/qgis-psc/), the Project Steering
Committee's list — plus an **all** view that merges the three: activity trends, the people behind the traffic, who works with
whom, the threads that ran longest, and the rhythm of a distributed project's
working week. Switch lists with the toggle in the header.

**→ [ismailsunni.id/qgis-lists-explorer](https://ismailsunni.id/qgis-lists-explorer/)**

|  | qgis-developer | qgis-user | qgis-psc | all |
|---|---|---|---|---|
| Messages | 68,529 | 56,473 | 10,835 | 135,837 |
| Threads | 16,895 | 16,415 | 1,747 | 33,355 |
| People | 2,044 | 4,873 | 166 | 6,234 |
| Span | 2006–2026 | 2008–2026 | 2008–2026 | 2006–2026 |

**all** is a real merge, not a sum: `parse.py all` reads the three archives
together, so identity merging and threading run across them. 849 people write on
more than one list and become one person; ~1,700 cross-posted discussions become
one thread (the "Logo" debate is 156 messages across psc and developer, where
each list alone shows half of it). The thread table gains a List column there.

## What it shows

| Section | Question it answers |
|---|---|
| Activity over time | How has list traffic changed? (drag to filter everything else) |
| Most active people | Who writes the most, in any period you pick? |
| When people write | Which weekday/hour does the project actually work? |
| Messages per person | How lopsided is participation? |
| Contributor table | Sortable, searchable per-person stats, time span, per-year sparkline |
| Who talks with whom | Co-participation graph: who shares threads with whom |
| Threads | Which discussions drew the most replies, and which never died? (sort any column) |
| Sender domains | Share of traffic by the domain people write from |
| Newcomers and regulars | Is the community renewing itself? |

The activity chart carries project milestones. Release dates (1.0 Kore, 2.0
Dufour, 3.0 Girona, 4.0 Norrköping) come from qgis.org; the infrastructure
markers — the first git workflow thread, the Trac→Redmine migration, the
"last call for switching to github issue tracker" — are dated from this archive
itself, and each tooltip says which. The PSC's founding is deliberately absent:
it was already active when the archive opens in 2006 and no date could be
sourced.

## Privacy

The archives are public, but that is not a reason to make personal data *more*
accessible than the source does. So:

- **No email addresses are published.** `docs/data/*.json` contains display names
  and the *domain* people write from, never an address — not even in the
  obfuscated `user at domain.com` form the archive itself uses. Addresses exist
  only in the local `raw/` mirror, which is gitignored, and are discarded after
  the identity merge.
- An address that a sender used *as* their display name is reduced to its local
  part, so no address leaks in through the back door.
- Display names and subject lines are reproduced as the archive publishes them.
- The page is marked `noindex`, because the OSGeo archive pages are
  (`<meta name="robots" content="noindex,follow">`): this tool should not make
  anyone easier to find by name than the source does. Remove that meta tag only
  if you decide otherwise on purpose.
- Anyone who would rather not appear can [open an issue](https://github.com/ismailsunni/qgis-lists-explorer/issues/new)
  and be removed.

The aggregate counts are statistics about a public technical forum, which is the
kind of processing GDPR Recital 162 and Art. 89 treat favourably — but that rests
on the data staying aggregated and proportionate, so keep it that way if you fork
this.

## How it works

`scripts/parse.py <list>` reads the monthly pipermail mbox archives from
`raw/<list>/` and writes one aggregated `docs/data/<list>.json`. The page is
static HTML/CSS/JS with hand-rolled SVG charts — no build step, no dependencies,
no tracking, no analytics.

Four parsing details worth knowing:

- **Dates.** Messages from before February 2008 have a `Date:` header clobbered by
  a list migration, so the envelope line is used when the header disagrees with the
  archive month.
- **Identity.** Addresses are the primary key, but addresses sharing the same full
  display name are merged into one person — several long-time contributors changed
  employer (and address) over the years. The table shows `+N` when a person's
  merged addresses span more than one domain.
- **The graph** joins two people when they appear in the same thread. It covers the
  80 most active people per list, keeps the 4,000 strongest pairs, and stores a
  per-year count for each, so the period filter and the bot toggle drive it like
  everything else. The layout is a deterministic force simulation — the same data
  always settles the same way, so filtering does not reshuffle the picture.
- **The thread table** sorts on any column, over a pool of the 400 largest threads
  plus the 300 longest-running — so a sort is "within the notable threads", not
  across all 16,000.
- **Threads** are rebuilt from `References`/`In-Reply-To`, falling back to
  normalised subjects within a 90-day window. Subjects with no content of their own
  ("(no subject)", one-word stubs) are excluded from that fallback, or they collect
  unrelated mail into one huge fake thread.
- **Bots.** A sender is flagged automated by the address it *mostly* posts from, so
  a human who once forwarded a Dropbox notification is still a human. Every
  aggregate is built twice, with and without them (`all` / `humans` in the JSON),
  so "hide automated senders" moves the charts too, not just the people list —
  on qgis-developer it removes 3,810 messages and 1,621 threads, most of them
  plugin-approval notifications.

## Updating the data

```sh
./scripts/update.sh                 # both lists
./scripts/update.sh qgis-user       # just one
```

Closed months are never re-fetched. A GitHub Action runs the same script on the
2nd of each month and commits the result; GitHub Pages serves `docs/` directly, so
a refreshed JSON is all a new deploy needs.

## Editing the page

`docs/index.html` links `app.js` and `style.css` with a content hash
(`app.js?v=…`). After editing either, run:

```sh
python3 scripts/stamp.py
```

Without it a deploy can hand a browser the new HTML beside a cached old script,
which fails in confusing ways. `update.sh` runs it for you.

## Local preview

```sh
python3 -m http.server -d docs 8000
```

## Caveats

Counts are "messages that reached the list", which is not the same as
contribution — much QGIS development moved to GitHub after ~2020, which the
traffic curve shows plainly. Sender domains say where mail comes from, not who
funds the work: free mail providers dominate both lists.
