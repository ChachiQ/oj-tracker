#!/usr/bin/env python3
"""Coderlands API probe script — Phase 0 diagnostic.

Usage:
    python scripts/probe_coderlands.py <JSESSIONID>

Explores exercise API structure, myls behaviour, and UUID resolution paths.
"""
import argparse
import json
import sys
import time

import requests

BASE_URL = "https://course.coderlands.com"
DELAY = 2  # seconds between requests


def api_request(session: requests.Session, method: str, path: str,
                label: str, **kwargs) -> dict | None:
    """Make an API call, print full response, return parsed JSON or None."""
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
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return data
        except ValueError:
            print(f"Non-JSON response ({len(resp.text)} chars):")
            print(resp.text[:2000])
            return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Coderlands API probe")
    parser.add_argument("jsessionid", help="JSESSIONID cookie value")
    args = parser.parse_args()

    session = requests.Session()
    jsessionid = args.jsessionid.strip()
    if jsessionid.lower().startswith("cookie:"):
        jsessionid = jsessionid[len("cookie:"):].strip()
    if "=" not in jsessionid:
        jsessionid = f"JSESSIONID={jsessionid}"
    session.headers["Cookie"] = jsessionid

    # ── Probe 1: exercise API — full response structure ──
    exercise = api_request(
        session, "POST",
        "/server/student/person/center/exercise",
        "Probe 1: exercise (full structure — look for classUuid/className per item)",
        json={},
    )

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
        "Probe 2: myls (current class — look for classInfo structure)",
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
            )
            time.sleep(DELAY)
    else:
        print("\n>>> No past classUuids found in exercise data — skipping Probe 3")
        # Try with a dummy to see error behaviour
        api_request(
            session, "GET",
            "/server/student/stady/myls?classUuid=00000000000000000000000000000000",
            "Probe 3: myls with dummy classUuid (error behaviour)",
        )
        time.sleep(DELAY)

    # ── Probe 4: listSubNew with bare problem number (expect failure) ──
    api_request(
        session, "GET",
        "/server/student/stady/listSubNew?problemUuid=1001",
        "Probe 4: listSubNew with bare number (expect failure)",
    )

    print(f"\n{'='*70}")
    print("Probe complete. Analyse exercise dataList items for cross-class UUID paths.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
