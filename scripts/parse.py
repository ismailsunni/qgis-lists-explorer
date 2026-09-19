#!/usr/bin/env python3
"""Parse the pipermail archives of one OSGeo list into an aggregated JSON file.

Usage: parse.py <list-name>   e.g. parse.py qgis-developer
Reads raw/<list-name>/*.txt[.gz], writes docs/data/<list-name>.json
"""
import email, gzip, json, os, re, sys, unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime, parseaddr

PIPERMAIL = "https://lists.osgeo.org/pipermail"
ALL_LISTS = ["qgis-developer", "qgis-user", "qgis-psc"]

LIST = sys.argv[1] if len(sys.argv) > 1 else "qgis-developer"
# "all" merges the lists into one dataset: identities and threads are unified
# across them, so a person on two lists is one person and a cross-posted
# discussion is one thread.
SOURCES = ALL_LISTS if LIST == "all" else [LIST]
OUT = f"docs/data/{LIST}.json"
LIST_URL = PIPERMAIL if LIST == "all" else f"{PIPERMAIL}/{LIST}"
GRAPH_NODES = 80     # people in the co-participation graph
GRAPH_EDGES = 4000   # strongest pairs kept

def dec(s):
    if not s:
        return ""
    try:
        return str(make_header(decode_header(s))).replace("\n", " ").strip()
    except Exception:
        return s.replace("\n", " ").strip()

def deobfuscate(addr):
    return re.sub(r"\s+at\s+", "@", addr or "", flags=re.I).strip().strip("<>").lower()

SUBJ_CLEAN = re.compile(
    r"^(?:\s*(?:re|aw|fwd?|antw|res|sv|vs|r)\s*[:\]]\s*|\s*\[qgis[- ]?(?:developer|user|psc)\]\s*)+", re.I)
def norm_subject(s):
    prev = None
    s = s or ""
    while prev != s:
        prev = s
        s = SUBJ_CLEAN.sub("", s).strip()
    return re.sub(r"\s+", " ", s).strip()

MSGID = re.compile(r"<([^<>@\s]+@[^<>\s]+)>")

# Many senders use their address as a display name. Keep the local part only, so
# no full address is ever published. See README > Privacy.
ADDR_ANY = re.compile(r"[A-Za-z0-9._%+-]+(?:@|\s+at\s+)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
def public_name(name):
    """Replace any address inside a display name with its local part alone."""
    out = ADDR_ANY.sub(lambda m: re.split(r"@|\s+at\s+", m.group(0))[0], name or "").strip()
    return re.sub(r"\s+", " ", out).strip(" ()<>,;:-") or "(unnamed)"


# ---------------------------------------------------------------- topics
# A transparent keyword taxonomy: the first pattern matching a thread's subject
# wins, so specific rules sit above cross-cutting ones (a crash report that
# mentions Windows is a bug, not an install question). The rules were built from
# the most frequent subject terms in these archives and are meant to be read and
# argued with — there is no model here. Roughly 82% of threads match something;
# the rest stay "unclassified" and the page says so.
TOPICS = [
    ("List admin & digests", r"\bdigest\b|unsubscrib|subscrib|out of office|auto.?reply|automatic reply|"
                             r"moderat|mailman|delivery status|undeliver|vacation"),
    ("Governance & funding", r"\bpsc\b|steering|\bvote|voting|ballot|election|nomination|\bagenda\b|minutes\b|"
                             r"budget|financial|\bgrant\b|sponsor|donation|funding|treasur|\bboard\b|motion|"
                             r"\bqep\b|trademark|foundation|membership|charter|by-?laws|certification|"
                             r"code of conduct|\bmeeting\b"),
    ("Community & events", r"\bgsoc\b|google summer|hackfest|foss4g|conference|user ?group|meetup|"
                           r"code ?sprint|mentor|contributor|welcome|introduc(e|tion)|survey\b|newsletter"),
    ("Docs & translation", r"documentation|\bdocs?\b|manual|tutorial|handbook|translat|transifex|i18n|l10n|"
                           r"localis|localiz|glossar|\btypo\b|screenshot"),
    ("Infrastructure", r"github|gitlab|\bgit\b|\bsvn\b|redmine|\btrac\b|issue ?tracker|bug ?tracker|jenkins|"
                       r"travis|\bci\b|continuous integration|mailing ?list|website|web ?site|qgis\.org|"
                       r"\bwiki\b|infrastructur|migration|hosting|\bdns\b|certificat|unit ?test|\btests?\b|"
                       r"test ?suite|\bqa\b|code ?review|pull ?request|\bpr\b\s|commit"),
    ("Releases & roadmap", r"release|freeze|\bltr\b|\brc\d?\b|backport|changelog|roadmap|milestone|"
                           r"what will be in|\bfreeze\b|feature ?freeze|release ?plan"),
    ("Install & platforms", r"install|osgeo4w|homebrew|\bdeb\b|debian|ubuntu|fedora|flatpak|\bsnap\b|nightly|"
                            r"\bbuild|cmake|compil|\bmakefile\b|dependenc|packag|windows|\bmac\b|macos|\bos ?x\b|"
                            r"linux|android|\bios\b|download|binary|portable|\bpath\b|startup|launch"),
    ("Plugins", r"plugin|repositor(y|ies) (approval|upload)|approval notification"),
    ("Processing & analysis", r"processing|sextante|algorithm|toolbox|\bgrass\b|\bsaga\b|\botb\b|geoprocess|"
                              r"model(l)?er|\bbatch\b|statistic|interpolat|raster calc|zonal|buffer|intersect|"
                              r"dissolve|overlay|network analys|classification|clip\b"),
    ("Python & API", r"python|pyqgis|\bapi\b|\bsip\b|binding|script|console|\bqt\d?\b|\bpyqt\b|\bc\+\+\b|"
                     r"signal|refactor|deprecat|\bcode\b|\bclass\b|\bmethod\b"),
    ("Web, server & basemaps", r"qgis[- ]?server|\bwms\b|\bwfs\b|\bwcs\b|\bwmts\b|\bows\b|web ?client|mapserver|"
                               r"geoserver|lizmap|\bproxy\b|tile|\bxyz\b|openlayers|google|bing|\bosm\b|"
                               r"openstreetmap|basemap|\bweb\b|online"),
    ("Data & formats", r"postgis|postgres|oracle|spatialite|geopackage|\bgpkg\b|shapefile|\bshp\b|\bgdal\b|"
                       r"\bogr\b|\bcsv\b|\bdxf\b|\bdwg\b|\becw\b|mrsid|geotiff|\bnetcdf\b|\bsqlite\b|\bmssql\b|"
                       r"db ?manager|data ?provider|\blidar\b|point ?cloud|\bmesh\b|database|\bsql\b|import|export"),
    ("Layers & rasters", r"\braster|\bvector\b|\blayers?\b|map ?canvas|\bcanvas\b|legend|project ?file|\bqgs\b|"
                         r"\bqgz\b|load(ing)? |\bmap\b|georeferenc|\bdem\b|\bwarp\b|mosaic|\btiff?\b|band\b"),
    ("Attributes & forms", r"attribute|\bform\b|\bfield\b|\btable\b|field ?calculator|expression|\bwidget\b|"
                           r"\bjoin\b|relation|\bfilter\b|\bquery\b|value ?map|\bnull\b"),
    ("CRS & projections", r"\bcrs\b|projection|reproject|\bepsg\b|\bproj4?\b|datum|transformation|"
                          r"coordinate ?system|on.the.fly|\butm\b|\bwgs ?84\b|coordinates?\b"),
    ("Symbology & rendering", r"symbol|styl(e|ing)|\bsld\b|\blabel|render|blend|categoriz|graduated|"
                              r"colou?r|\bsvg\b|marker|opacity|transparen|\bsplash\b|\bicon\b|\btheme\b"),
    ("Layouts & printing", r"composer|layout|atlas|print|\bpdf\b|\bdpi\b|scale ?bar|north ?arrow|export image"),
    ("Editing & geometry", r"digiti[sz]|editing|\bsnap(ping)?\b|topolog|geometr|vertex|vertice|node tool|"
                           r"split feature|merge feature|\bpolygon|\bline(s)?\b|\bpoints?\b|\bfeatures?\b|"
                           r"\bselect(ion)?\b|\barea\b|\blength\b"),
    ("GPS & field data", r"\bgps\b|\bgpx\b|garmin|field ?data|tracker|waypoint|\bnmea\b"),
    ("Bugs & performance", r"crash|segfault|segmentation|freez|hang|broken|regression|\bbug\b|traceback|"
                           r"does ?n.?t work|not working|fail(s|ed|ure)?\b|\bslow\b|performance|memory|"
                           r"optimi[sz]|benchmark|leak\b"),
    ("UI & usability", r"\bui\b|\bgui\b|dialog|toolbar|\bmenu\b|shortcut|usability|user ?interface|"
                       r"\bpanel\b|\bbrowser\b|drag ?and ?drop|\bzoom\b|\bpan\b"),
]
ORDER = ['List admin & digests', 'Governance & funding', 'Community & events', 'Docs & translation', 'Plugins', 'Infrastructure', 'Processing & analysis', 'Python & API', 'Web, server & basemaps', 'Data & formats', 'CRS & projections', 'Symbology & rendering', 'Layouts & printing', 'Attributes & forms', 'Editing & geometry', 'GPS & field data', 'Layers & rasters', 'Bugs & performance', 'Releases & roadmap', 'Install & platforms', 'UI & usability']
TOPICS = sorted(TOPICS, key=lambda t: ORDER.index(t[0]))
TOPICS = [(n, re.compile(p, re.I)) for n, p in TOPICS]
def classify(s):
    for n, p in TOPICS:
        if p.search(s):
            return n
    return "unclassified"


class UF:
    def __init__(self): self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[rb] = ra

FROM_LINE = re.compile(r"^From \S+(?: at \S+)? +\w{3} \w{3} +\d+ \d\d:\d\d:\d\d \d{4}\s*$")

def iter_messages(path):
    """Pipermail mbox: split on envelope 'From ' lines, parse each chunk."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as fh:
        text = fh.read().decode("utf-8", "replace")
    chunk = []
    for line in text.splitlines(True):
        if FROM_LINE.match(line):
            if chunk:
                yield chunk[0], email.message_from_string("".join(chunk[1:]))
            chunk = [line]
        elif chunk:
            chunk.append(line)
    if chunk:
        yield chunk[0], email.message_from_string("".join(chunk[1:]))

ENV_DATE = re.compile(r"(\w{3} \w{3} +\d+ \d\d:\d\d:\d\d \d{4})\s*$")

def envelope_date(line):
    m = ENV_DATE.search(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%a %b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

month_name = "January February March April May June July August September October November December".split()

def archive_span():
    """Earliest and latest archive month across every list, so each dataset can
    draw its timeline on one shared axis instead of its own."""
    stems = []
    for src in ALL_LISTS:
        d = f"raw/{src}"
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith(".txt") or f.endswith(".txt.gz"):
                y, mn = f.replace(".txt.gz", "").replace(".txt", "").split("-")
                stems.append((int(y), month_name.index(mn) + 1))
    if not stems:
        return None
    lo, hi = min(stems), max(stems)
    return dict(first=f"{lo[0]}-{lo[1]:02d}", last=f"{hi[0]}-{hi[1]:02d}")


def main():
    files = [(src, f) for src in SOURCES
             for f in sorted(os.listdir(f"raw/{src}"))
             if f.endswith(".txt") or f.endswith(".txt.gz")]
    msgs = []
    for src, fn in files:
        stem = fn.replace(".txt.gz", "").replace(".txt", "")
        arch_year, arch_month = stem.split("-")
        arch_ym = (int(arch_year), month_name.index(arch_month) + 1)
        for env, m in iter_messages(os.path.join(f"raw/{src}", fn)):
            frm = dec(m.get("From", ""))
            # pipermail rewrites From as: "user at domain.com (Display Name)".
            # The name itself may contain brackets, so take the FIRST "(".
            paren = re.match(r"^(.*?)\s*\((.*)\)\s*$", frm)
            if paren:
                addr, name = paren.group(1).strip(), paren.group(2).strip()
            else:
                # parseaddr mangles the "user at domain" form, so only trust it
                # when the header carries a real <addr-spec>.
                name, a = parseaddr(frm)
                addr = a if "@" in a else frm
            email_addr = deobfuscate(addr)
            if not email_addr or "@" not in email_addr:
                email_addr = "unknown@unknown"
            name = dec(name) or email_addr.split("@")[0]
            # The Date: header of pre-2008 messages was clobbered by a list
            # migration; the envelope line and the archive month are reliable.
            try:
                dt = parsedate_to_datetime(m.get("Date"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = None
            env_dt = envelope_date(env)
            cands = [d for d in (dt, env_dt) if d and 2000 < d.year < 2100]
            dt = next((d for d in cands if (d.year, d.month) == arch_ym), None) \
                 or next((d for d in cands), None)
            if dt is None:
                continue
            mid = MSGID.search(m.get("Message-ID", "") or "")
            mid = mid.group(1) if mid else f"synthetic-{len(msgs)}"
            refs = MSGID.findall((m.get("References", "") or "") + " " + (m.get("In-Reply-To", "") or ""))
            msgs.append(dict(mid=mid, refs=refs, name=name, email=email_addr,
                             subj=dec(m.get("Subject", "")), ts=dt, archive=stem, src=src))
    msgs.sort(key=lambda x: x["ts"])

    # ---- identity: one person may post from several addresses ----
    names_by_email = defaultdict(Counter)
    for m in msgs:
        names_by_email[m["email"]][m["name"]] += 1
    def norm_name(n):
        n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z ]", "", n.lower()).strip()
    ident = UF()
    by_name = {}
    for em, names in names_by_email.items():
        ident.find(em)
        nn = norm_name(names.most_common(1)[0][0])
        if " " in nn and len(nn) > 4:
            if nn in by_name:
                ident.union(by_name[nn], em)
            else:
                by_name[nn] = em
    for m in msgs:
        m["pid"] = ident.find(m["email"])
    print(f"parsed {len(msgs)} messages from {len(files)} archives "
          f"({', '.join(SOURCES)})", file=sys.stderr)

    # ---- threading: union-find on references, fallback to normalised subject ----
    uf = UF()
    by_mid = {}
    for m in msgs:
        uf.find(m["mid"])
        by_mid.setdefault(m["mid"], m)
    for m in msgs:
        for r in m["refs"]:
            uf.union(r, m["mid"])
    NO_SUBJECT = re.compile(r"^\(?(no subject|none|\(none\)|untitled)\)?$", re.I)
    last_subj = {}
    for m in msgs:
        ns = norm_subject(m["subj"])
        m["ns"] = ns
        if not ns or NO_SUBJECT.match(ns) or len(ns) < 4:
            continue
        prev = last_subj.get(ns)
        if prev and (m["ts"] - prev["ts"]).days <= 90:
            if not m["refs"] or uf.find(prev["mid"]) != uf.find(m["mid"]):
                uf.union(prev["mid"], m["mid"])
        last_subj[ns] = m

    threads = defaultdict(list)
    for m in msgs:
        threads[uf.find(m["mid"])].append(m)

    # ---- people ----
    authors = {}
    for m in msgs:
        a = authors.setdefault(m["pid"], dict(emails=Counter(), names=Counter(), n=0,
                                              years=Counter(), first=m["ts"], last=m["ts"],
                                              started=0, threads=set()))
        a["names"][m["name"]] += 1
        a["emails"][m["email"]] += 1
        a["n"] += 1
        a["years"][m["ts"].year] += 1
        a["last"] = m["ts"]
        a["threads"].add(uf.find(m["mid"]))
    for ms in threads.values():
        ms.sort(key=lambda x: x["ts"])
        authors[ms[0]["pid"]]["started"] += 1

    BOT_LOCAL = re.compile(r"^(noreply|no-reply|do-?not-?reply|jenkins|travis|mailman|"
                           r"bounces|postmaster|root|notifications?|automation)\b")
    def is_bot(email):
        """Judge on the address someone mostly posts from: a human who once got
        a dropbox notification forwarded is not a bot."""
        return bool(BOT_LOCAL.match(email.split("@")[0])) or email.split("@")[-1].endswith("github.com")

    bot_pids = {p for p, a in authors.items() if is_bot(a["emails"].most_common(1)[0][0])}
    name_of = {p: public_name(a["names"].most_common(1)[0][0]) for p, a in authors.items()}
    years = sorted({m["ts"].year for m in msgs})

    def dedup(ts):
        seen, out = set(), []
        for t in ts:
            k = (t["subject"], t["start"])
            if k not in seen:
                seen.add(k)
                out.append(t)
        return out

    def view(sel):
        """Every aggregate, recomputed over whichever messages are in play — so
        hiding automated senders moves the charts, not just the people count."""
        monthly = Counter()
        m_people, m_threads = defaultdict(set), defaultdict(set)
        hourly_year, domains_year = defaultdict(Counter), defaultdict(Counter)
        active, first_year = defaultdict(set), {}
        grouped = defaultdict(list)
        for m in sel:
            y, key, root = m["ts"].year, m["ts"].strftime("%Y-%m"), uf.find(m["mid"])
            monthly[key] += 1
            m_people[key].add(m["pid"])
            m_threads[key].add(root)
            hourly_year[y][(m["ts"].weekday(), m["ts"].hour)] += 1
            domains_year[m["email"].split("@")[-1]][y] += 1
            active[y].add(m["pid"])
            first_year[m["pid"]] = min(first_year.get(m["pid"], y), y)
            grouped[root].append(m)

        thread_list = []
        topic_year, topic_msgs = defaultdict(Counter), Counter()
        for ms in grouped.values():
            starter = ms[0]
            topic = classify(norm_subject(starter["subj"]))
            topic_year[topic][starter["ts"].year] += 1
            topic_msgs[topic] += len(ms)
            thread_list.append(dict(
                subject=norm_subject(starter["subj"]) or "(no subject)",
                n=len(ms),
                people=len({x["pid"] for x in ms}),
                start=ms[0]["ts"].strftime("%Y-%m-%d"),
                end=ms[-1]["ts"].strftime("%Y-%m-%d"),
                days=(ms[-1]["ts"] - ms[0]["ts"]).days,
                starter=name_of[starter["pid"]],
                topic=topic,
                list=starter["src"],
                url=f"{PIPERMAIL}/{starter['src']}/{starter['archive']}/thread.html",
            ))
        # ---- co-participation graph ----
        # Who shares threads with whom, among the people who write most. Edges
        # keep a per-year breakdown so the period filter drives the graph too.
        msg_count = Counter(m["pid"] for m in sel)
        pid_years = defaultdict(Counter)
        for m in sel:
            pid_years[m["pid"]][m["ts"].year] += 1
        top = [p for p, _ in msg_count.most_common(GRAPH_NODES)]
        idx = {p: i for i, p in enumerate(top)}
        edges = defaultdict(Counter)
        for ms in grouped.values():
            here = sorted({idx[m["pid"]] for m in ms if m["pid"] in idx})
            if len(here) < 2:
                continue
            y = str(ms[0]["ts"].year)
            for a in range(len(here)):
                for b in range(a + 1, len(here)):
                    edges[(here[a], here[b])][y] += 1

        started = Counter(t["start"][:4] for t in thread_list)
        newcomers = Counter(first_year.values())

        return dict(
            graph=dict(
                nodes=[dict(name=name_of[p], domain=authors[p]["emails"].most_common(1)[0][0].split("@")[-1],
                            years={str(k): v for k, v in sorted(pid_years[p].items())})
                       for p in top],
                edges=[[a, b, dict(ys)] for (a, b), ys in
                       sorted(edges.items(), key=lambda kv: -sum(kv[1].values()))[:GRAPH_EDGES]],
            ),
            topics=[dict(t=t, n=sum(c.values()), msgs=topic_msgs[t],
                         years={str(k): v for k, v in sorted(c.items())})
                    for t, c in sorted(topic_year.items(), key=lambda kv: -sum(kv[1].values()))],
            monthly=[dict(m=k, n=monthly[k], p=len(m_people[k]), t=len(m_threads[k]))
                     for k in sorted(monthly)],
            yearly=[dict(y=y, n=sum(v for k, v in monthly.items() if k.startswith(str(y))),
                         threads=started[str(y)], people=len(active[y]),
                         newcomers=newcomers[y], returning=len(active[y] & active[y - 1]))
                    for y in years],
            # One pool the table can sort any way: the biggest threads by reply
            # count, plus the longest-running ones that a size cut would miss.
            threads=dedup(sorted(thread_list, key=lambda t: -t["n"])[:400]
                          + sorted([t for t in thread_list if t["n"] >= 5],
                                   key=lambda t: -t["days"])[:300]),
            heatmapByYear={str(y): [[c[(d, h)] for h in range(24)] for d in range(7)]
                           for y, c in hourly_year.items()},
            domains=[dict(d=d, n=sum(c.values()), years={str(k): v for k, v in sorted(c.items())})
                     for d, c in sorted(domains_year.items(), key=lambda kv: -sum(kv[1].values()))[:60]],
        )

    out = dict(
        meta=dict(
            generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            list=LIST, listUrl=LIST_URL, sources=SOURCES, span=archive_span(),
            messages=len(msgs), threads=len(threads), people=len(authors),
            bots=len(bot_pids),
            first=msgs[0]["ts"].strftime("%Y-%m-%d"), last=msgs[-1]["ts"].strftime("%Y-%m-%d"),
            archives=len(files),
        ),
        years=years,
        # Addresses are deliberately NOT published: only the domain, which is
        # what the analysis actually needs. See README > Privacy.
        authors=[dict(name=name_of[p],
                      domain=a["emails"].most_common(1)[0][0].split("@")[-1],
                      domains=len({e.split("@")[-1] for e in a["emails"]}),
                      bot=(p in bot_pids) or None, n=a["n"],
                      started=a["started"], threads=len(a["threads"]),
                      first=a["first"].strftime("%Y-%m"), last=a["last"].strftime("%Y-%m"),
                      years={str(k): v for k, v in sorted(a["years"].items())})
                 for p, a in sorted(authors.items(), key=lambda kv: -kv[1]["n"])],
        all=view(msgs),
        humans=view([m for m in msgs if m["pid"] not in bot_pids]),
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB): "
          f"{out['meta']['messages']} msgs, {out['meta']['threads']} threads, "
          f"{out['meta']['people']} people", file=sys.stderr)

main()
