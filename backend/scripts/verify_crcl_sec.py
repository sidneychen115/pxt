"""Verify CRCL SEC EDGAR XBRL vs Circle Q1 2026 10-Q (official thousands USD)."""
import json
import urllib.request

UA = {"User-Agent": "pxt-research imxichen@example.com"}
CIK = "0001876042"

# Official 10-Q (filed 2026-05-11), values in thousands USD
OFFICIAL_10Q = {
    "2026-03-31": {
        "total_revenue_and_reserve_income": 694_133,
        "reserve_income": 652_508,
        "other_revenue": 41_625,
        "net_income_continuing": 55_246,  # after tax; before tax = 56,685
        "operating_income_continuing": 45_002,
        "diluted_eps": 0.21,
    },
    "2025-03-31": {
        "total_revenue_and_reserve_income": 578_573,
        "reserve_income": 557_911,
        "other_revenue": 20_662,
        "net_income_continuing": 64_791,
        "operating_income_continuing": 92_940,
    },
    "2025-12-31": {
        "total_revenue_and_reserve_income": 770_232,  # Q4 single quarter
    },
}

# For 2025-12-31 quarterly pick, require Q4 frame (not FY annual)
FRAME_HINT = {
    "2026-03-31": "CY2026Q1",
    "2025-03-31": "CY2025Q1",
    "2025-12-31": "CY2025Q4",
}

# Map official keys -> us-gaap tags to test
TAG_MAP = {
    "total_revenue_and_reserve_income": "Revenues",
    "other_revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "net_income_continuing": "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
    "operating_income_continuing": "OperatingIncomeLoss",
    "diluted_eps": "EarningsPerShareDiluted",
}


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def pick_quarterly_fact(items: list[dict], end: str) -> dict | None:
    """Prefer 10-Q row with calendar-quarter frame (single quarter, not YTD/FY)."""
    hint = FRAME_HINT.get(end)
    if hint:
        exact = [
            x
            for x in items
            if x.get("end") == end and x.get("frame") == hint and x.get("form") == "10-Q"
        ]
        if exact:
            return max(exact, key=lambda x: x.get("filed", ""))
    candidates = [
        x
        for x in items
        if x.get("end") == end and x.get("form") == "10-Q" and x.get("fp") in ("Q1", "Q2", "Q3", "Q4")
    ]
    if not candidates:
        candidates = [x for x in items if x.get("end") == end and x.get("form") in ("10-Q", "10-K")]
    if not candidates:
        return None
    framed = [x for x in candidates if x.get("frame")]
    pool = framed if framed else candidates
    return max(pool, key=lambda x: x.get("filed", ""))


def main() -> None:
    data = fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json")
    print("Entity:", data.get("entityName"))
    print()

    usgaap = data["facts"]["us-gaap"]
    mismatches = []

    for period, official in OFFICIAL_10Q.items():
        print(f"=== Period end {period} ===")
        for key, official_val in official.items():
            tag = TAG_MAP.get(key)
            if not tag or tag not in usgaap:
                print(f"  {key}: SKIP (tag {tag!r} missing)")
                continue
            unit_items = usgaap[tag]["units"]
            items = unit_items.get("USD") or unit_items.get("USD/shares") or next(iter(unit_items.values()))
            row = pick_quarterly_fact(items, period)
            if not row:
                print(f"  {key} ({tag}): SEC row NOT FOUND")
                mismatches.append((period, key, "missing"))
                continue
            sec_val = row["val"]
            # 10-Q reports thousands; SEC companyfacts uses full USD
            official_usd = official_val * 1000 if key != "diluted_eps" else official_val
            if key == "diluted_eps":
                match = abs(sec_val - official_val) < 0.001
            else:
                match = sec_val == official_usd
            status = "OK" if match else "MISMATCH"
            if not match:
                mismatches.append((period, key, sec_val, official_usd))
            print(
                f"  {key} ({tag}): SEC={sec_val:,} official={official_usd:,} "
                f"frame={row.get('frame')} filed={row.get('filed')} [{status}]"
            )
        print()

    # Reserve income: search custom/dei tags
    print("=== Reserve income (may use custom taxonomy) ===")
    for ns_name, ns in data["facts"].items():
        if ns_name == "us-gaap":
            continue
        for tag, body in ns.items():
            if "reserve" in tag.lower() and "income" in tag.lower():
                for unit, items in body.get("units", {}).items():
                    row = pick_quarterly_fact(items, "2026-03-31")
                    if row:
                        print(f"  {ns_name}:{tag} = {row['val']:,} (official reserve 652,508)")

    # Show duplicate Revenues rows for 2025-09-30 (YTD vs quarterly issue)
    print()
    print("=== Duplicate check: 2025-09-30 Revenues (YTD vs quarter) ===")
    rev_items = usgaap["Revenues"]["units"]["USD"]
    for x in sorted(
        [i for i in rev_items if i.get("end") == "2025-09-30" and i.get("form") == "10-Q"],
        key=lambda i: i.get("val", 0),
        reverse=True,
    ):
        print(
            f"  val={x['val']:,} fp={x.get('fp')} frame={x.get('frame')} filed={x.get('filed')}"
        )
    print("  Official Q3 2025 quarter only: 739,759 thousands")

    print()
    if mismatches:
        print("RESULT: ISSUES FOUND", len(mismatches))
        for m in mismatches:
            print(" ", m)
    else:
        print("RESULT: All mapped us-gaap tags match official 10-Q for tested periods.")


if __name__ == "__main__":
    main()
