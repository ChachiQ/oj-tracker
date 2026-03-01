#!/usr/bin/env python3
"""Coderlands API probe script — Phase 0 diagnostic.

Usage:
    python scripts/probe_coderlands.py <JSESSIONID>
    python scripts/probe_coderlands.py <JSESSIONID> --check P1610933,P1610934,P1610818

Explores exercise API structure, myls behaviour, and UUID resolution paths.
With --check, diagnoses why specific problems are missing from sync.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

import requests

BASE_URL = "https://course.coderlands.com"
DELAY = 2  # seconds between requests
_PNO_RE = re.compile(r'^P?(\d+)$', re.IGNORECASE)


def api_request(session: requests.Session, method: str, path: str,
                label: str, quiet: bool = False, **kwargs) -> dict | None:
    """Make an API call, print full response, return parsed JSON or None.

    If quiet=True, suppress the full JSON dump (useful for large responses).
    """
    url = f"{BASE_URL}{path}"
    print(f"\n{'='*70}")
    print(f"[{label}]  {method} {path}")
    print(f"{'='*70}")

    try:
        if method == "GET":
            resp = session.get(url, timeout=30, **kwargs)
        else:
            resp = session.post(url, timeout=30, **kwargs)

        print(f"Status: {resp.status_code}")
        resp.encoding = "utf-8"

        try:
            data = resp.json()
            if not quiet:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            return data
        except ValueError:
            print(f"Non-JSON response ({len(resp.text)} chars):")
            print(resp.text[:2000])
            return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def parse_problem_ids(raw: str) -> set[str]:
    """Parse comma-separated problem IDs, strip P prefix, return bare numbers."""
    ids = set()
    for token in re.split(r'[,\s]+', raw):
        token = token.strip()
        if not token:
            continue
        m = _PNO_RE.match(token)
        if m:
            ids.add(m.group(1))
        else:
            print(f"WARNING: cannot parse problem ID '{token}', skipping")
    return ids


def extract_exercise_problem_ids(exercise_resp: dict | None) -> tuple[set[str], set[str], int]:
    """Extract all problem IDs from exercise API response.

    Returns (ac_ids, unac_ids, dataList_count).
    """
    ac_ids: set[str] = set()
    unac_ids: set[str] = set()
    data_list = []

    if exercise_resp and isinstance(exercise_resp.get("result"), dict):
        data_list = exercise_resp["result"].get("dataList", [])
    elif exercise_resp and isinstance(exercise_resp.get("result"), list):
        data_list = exercise_resp["result"]

    for item in data_list:
        if not isinstance(item, dict):
            continue
        ac_str = item.get("acStr", "") or ""
        unac_str = item.get("unAcStr", "") or ""
        for pid in re.split(r'[,\s]+', ac_str):
            pid = pid.strip()
            if pid:
                m = _PNO_RE.match(pid)
                ac_ids.add(m.group(1) if m else pid)
        for pid in re.split(r'[,\s]+', unac_str):
            pid = pid.strip()
            if pid:
                m = _PNO_RE.match(pid)
                unac_ids.add(m.group(1) if m else pid)

    return ac_ids, unac_ids, len(data_list)


def check_get_probelm_uuid(session: requests.Session, problem_no: str) -> str | None:
    """Call getProbelmUuid API for a single problem number. Returns UUID or None."""
    url = f"{BASE_URL}/server/student/person/center/getProbelmUuid"
    try:
        resp = session.post(
            url, timeout=30,
            data=f"problemNo=P{problem_no}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.encoding = "utf-8"
        data = resp.json()
        # Response may be flat {isSuccess, data} or wrapped {code, result: {isSuccess, data}}
        inner = data
        if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
            inner = data["result"]
        if isinstance(inner, dict) and inner.get("isSuccess") == "1":
            uuid = inner.get("data", "")
            if uuid and re.match(r'^[0-9a-fA-F]{32}$', uuid):
                return uuid
        return None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Coderlands API probe")
    parser.add_argument("jsessionid", help="JSESSIONID cookie value")
    parser.add_argument(
        "--check", "-c", default="",
        help="Comma-separated problem IDs to diagnose (e.g. P1610933,P1610934,P1610818)",
    )
    args = parser.parse_args()

    session = requests.Session()
    jsessionid = args.jsessionid.strip()
    if jsessionid.lower().startswith("cookie:"):
        jsessionid = jsessionid[len("cookie:"):].strip()
    if "=" not in jsessionid:
        jsessionid = f"JSESSIONID={jsessionid}"
    session.headers["Cookie"] = jsessionid

    # Parse target problem IDs if provided
    target_ids = parse_problem_ids(args.check) if args.check else set()

    # ── Probe 1: exercise API — full response structure ──
    # If checking specific problems, suppress full dump (can be huge)
    exercise = api_request(
        session, "POST",
        "/server/student/person/center/exercise",
        "Probe 1: exercise API",
        quiet=bool(target_ids),
        json={},
    )

    # Extract all problem IDs from exercise
    ac_ids, unac_ids, data_list_count = extract_exercise_problem_ids(exercise)
    all_exercise_ids = ac_ids | unac_ids

    print(f"\n>>> exercise dataList items: {data_list_count}")
    print(f">>> AC problems: {len(ac_ids)}")
    print(f">>> unAC problems: {len(unac_ids)}")
    print(f">>> Total unique problems: {len(all_exercise_ids)}")

    if target_ids:
        print(f"\n{'─'*70}")
        print(f"TARGET PROBLEM DIAGNOSIS")
        print(f"{'─'*70}")
        for pid in sorted(target_ids):
            in_ac = pid in ac_ids
            in_unac = pid in unac_ids
            if in_ac:
                status = "FOUND in acStr (AC)"
            elif in_unac:
                status = "FOUND in unAcStr (not AC)"
            else:
                status = "MISSING from exercise API"
            print(f"  P{pid}: {status}")

    # Extract classUuids from exercise items if present
    class_uuids_from_exercise: set[str] = set()
    if exercise and isinstance(exercise.get("result"), dict):
        data_list = exercise["result"].get("dataList", [])
        for item in data_list:
            if isinstance(item, dict):
                for key in ("classUuid", "classId", "className", "classInfo"):
                    if key in item:
                        print(f"\n>>> exercise item has key '{key}': {item[key]}")
                        if key == "classUuid":
                            class_uuids_from_exercise.add(item[key])

    time.sleep(DELAY)

    # ── Probe 2: myls — current class lessons ──
    myls = api_request(
        session, "GET",
        "/server/student/stady/myls",
        "Probe 2: myls (current class)",
        quiet=bool(target_ids),
    )

    current_class_uuid = ""
    if myls and isinstance(myls.get("result"), dict):
        class_info = myls["result"].get("classInfo", {})
        if isinstance(class_info, dict):
            current_class_uuid = class_info.get("uuid", "")
            print(f"\n>>> Current classUuid: {current_class_uuid}")
            print(f">>> classInfo keys: {list(class_info.keys())}")

    time.sleep(DELAY)

    # ── Probe 3: myls with past classUuid (if found from exercise) ──
    past_uuids = class_uuids_from_exercise - {current_class_uuid}
    if past_uuids:
        for cuuid in list(past_uuids)[:2]:  # test up to 2 past classes
            api_request(
                session, "GET",
                f"/server/student/stady/myls?classUuid={cuuid}",
                f"Probe 3: myls with past classUuid={cuuid[:12]}...",
                quiet=bool(target_ids),
            )
            time.sleep(DELAY)
    else:
        print("\n>>> No past classUuids found in exercise data — skipping Probe 3")
        if not target_ids:
            api_request(
                session, "GET",
                "/server/student/stady/myls?classUuid=00000000000000000000000000000000",
                "Probe 3: myls with dummy classUuid (error behaviour)",
            )
            time.sleep(DELAY)

    # ── Probe 4: listSubNew with bare problem number (expect failure) ──
    if not target_ids:
        api_request(
            session, "GET",
            "/server/student/stady/listSubNew?problemUuid=1001",
            "Probe 4: listSubNew with bare number (expect failure)",
        )
        time.sleep(DELAY)

    # ── Probe 5: getProbelmUuid verification for target problems ──
    if target_ids:
        print(f"\n{'='*70}")
        print(f"Probe 5: getProbelmUuid verification")
        print(f"{'='*70}")

        uuid_results: dict[str, str | None] = {}
        for pid in sorted(target_ids):
            print(f"\n  P{pid}: calling getProbelmUuid...", end=" ")
            uuid = check_get_probelm_uuid(session, pid)
            uuid_results[pid] = uuid
            if uuid:
                print(f"OK → {uuid}")
            else:
                print("FAILED (no UUID returned)")
            time.sleep(DELAY)

        # ── Summary ──
        print(f"\n{'='*70}")
        print("DIAGNOSIS SUMMARY")
        print(f"{'='*70}")
        print(f"exercise API: {len(all_exercise_ids)} total problems "
              f"({len(ac_ids)} AC, {len(unac_ids)} unAC)")
        print()

        for pid in sorted(target_ids):
            in_exercise = pid in all_exercise_ids
            has_uuid = uuid_results[pid] is not None
            print(f"  P{pid}:")
            print(f"    exercise API: {'YES' if in_exercise else 'NO ← ROOT CAUSE: not in exercise'}")
            print(f"    getProbelmUuid: {'YES → ' + uuid_results[pid] if has_uuid else 'NO ← problem may not exist on platform'}")

            if not in_exercise and has_uuid:
                print(f"    → VERDICT: Problem exists but exercise API doesn't return it.")
                print(f"               Need alternative discovery mechanism.")
            elif not in_exercise and not has_uuid:
                print(f"    → VERDICT: Problem not found anywhere. Check problem ID is correct.")
            elif in_exercise and has_uuid:
                print(f"    → VERDICT: Should sync normally. Check scraper filtering logic.")
            elif in_exercise and not has_uuid:
                print(f"    → VERDICT: In exercise but UUID resolution fails. Check UUID logic.")
    else:
        print(f"\n{'='*70}")
        print("Probe complete. Analyse exercise dataList items for cross-class UUID paths.")
        print(f"{'='*70}")
        print("\nTip: Use --check P1610933,P1610934 to diagnose specific missing problems.")


if __name__ == "__main__":
    main()
