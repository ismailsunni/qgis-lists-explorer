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

LIST = sys.argv[1] if len(sys.argv) > 1 else "qgis-developer"
RAW = f"raw/{LIST}"
OUT = f"docs/data/{LIST}.json"
LIST_URL = f"https://lists.osgeo.org/pipermail/{LIST}"

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
    r"^(?:\s*(?:re|aw|fwd?|antw|res|sv|vs|r)\s*[:\]]\s*|\s*\[qgis[- ]?(?:developer|user)\]\s*)+", re.I)
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

def main():
    files = sorted(f for f in os.listdir(RAW) if f.endswith(".txt") or f.endswith(".txt.gz"))
    msgs = []
    for fn in files:
        stem = fn.replace(".txt.gz", "").replace(".txt", "")
        arch_year, arch_month = stem.split("-")
        arch_ym = (int(arch_year), month_name.index(arch_month) + 1)
        for env, m in iter_messages(os.path.join(RAW, fn)):
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
                             subj=dec(m.get("Subject", "")), ts=dt, archive=stem))
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
    print(f"parsed {len(msgs)} messages from {len(files)} archives", file=sys.stderr)

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
        for ms in grouped.values():
            starter = ms[0]
            thread_list.append(dict(
                subject=norm_subject(starter["subj"]) or "(no subject)",
                n=len(ms),
                people=len({x["pid"] for x in ms}),
                start=ms[0]["ts"].strftime("%Y-%m-%d"),
                end=ms[-1]["ts"].strftime("%Y-%m-%d"),
                days=(ms[-1]["ts"] - ms[0]["ts"]).days,
                starter=name_of[starter["pid"]],
                url=f"{LIST_URL}/{starter['archive']}/thread.html",
            ))
        started = Counter(t["start"][:4] for t in thread_list)
        newcomers = Counter(first_year.values())

        return dict(
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
            list=LIST, listUrl=LIST_URL,
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
