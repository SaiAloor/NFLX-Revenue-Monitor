"""Find and download Netflix earnings letters from SEC EDGAR.

Netflix files each quarterly letter as Exhibit 99.1 to an 8-K under Item 2.02
("Results of Operations"). EDGAR's submissions feed lists those filings; the
filing's index lists its documents, and the exhibit is the one named like
ex991_q326.htm.

The SEC asks every automated client to send a User-Agent with contact details
and to stay under 10 requests a second, so set SEC_USER_AGENT.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

import requests

CIK = "1065280"  # Netflix, Inc.
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{int(CIK):010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"
EXHIBIT_RE = re.compile(r"ex[-_]?99[-_.]?0?1.*\.html?$", re.IGNORECASE)


@dataclass
class Filing:
    accession: str      # 0001065280-26-000290
    filing_date: str    # 2026-10-20
    url: str = ""       # exhibit 99.1, once found


class SecClient:
    def __init__(self, user_agent: str | None = None, pause: float = 0.2):
        ua = user_agent or os.environ.get("SEC_USER_AGENT")
        if not ua:
            raise RuntimeError("Set SEC_USER_AGENT to 'Your Name your@email.com' (SEC requirement).")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
        self.pause = pause

    def _get(self, url: str) -> requests.Response:
        for attempt in range(3):
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            time.sleep(self.pause)
            return resp
        resp.raise_for_status()
        return resp

    def earnings_filings(self) -> list[Filing]:
        """8-K filings with Item 2.02, newest first."""
        recent = self._get(SUBMISSIONS_URL).json()["filings"]["recent"]
        out = []
        for form, acc, date, items in zip(
            recent["form"], recent["accessionNumber"], recent["filingDate"], recent["items"]
        ):
            if form == "8-K" and "2.02" in (items or ""):
                out.append(Filing(accession=acc, filing_date=date))
        return out

    def find_letter(self, filing: Filing) -> Filing:
        acc = filing.accession.replace("-", "")
        index = self._get(ARCHIVE_URL.format(cik=CIK, acc=acc, name="index.json")).json()
        names = [item["name"] for item in index["directory"]["item"]]
        exhibits = [n for n in names if EXHIBIT_RE.search(n)]
        if not exhibits:
            raise LookupError(f"no Exhibit 99.1 in filing {filing.accession}: {names}")
        filing.url = ARCHIVE_URL.format(cik=CIK, acc=acc, name=sorted(exhibits)[0])
        return filing

    def download(self, url: str) -> bytes:
        return self._get(url).content
