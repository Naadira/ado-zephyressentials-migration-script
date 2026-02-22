import requests
import json
import os
import time
from requests.auth import HTTPBasicAuth

# =====================================================
# CONFIGURATION (same as your original)
# =====================================================

ADO_ORG = "HESource"
ADO_PROJECT = "Source"
ADO_PAT = ""
ADO_TEST_PLAN_ID = 605030

ZEPHYR_BASE_URL = "https://prod-api.zephyr4jiracloud.com/v2"
ZEPHYR_API_TOKEN = ""
JIRA_PROJECT_KEY = "ANR"

STATE_FILE = "plan_migration_state.json"

REQUEST_TIMEOUT = 60
MAX_RETRIES = 5
RETRY_DELAY = 5


# =====================================================
# STATE MANAGEMENT (same structure)
# =====================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "folders": {},
            "cycles": {},
            "testcases": {},
            "executions": {},
            "last_suite": None,
            "last_tc": None
        }

    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)

    except Exception:
        print("⚠️ State file corrupted — resetting safely")
        return {
            "folders": {},
            "cycles": {},
            "testcases": {},
            "executions": {},
            "last_suite": None,
            "last_tc": None
        }

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

state = load_state()


# =====================================================
# HELPERS
# =====================================================

def zephyr_headers():
    return {
        "Authorization": f"Bearer {ZEPHYR_API_TOKEN}",
        "Content-Type": "application/json"
    }

def safe_get(url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(
                url,
                auth=HTTPBasicAuth("naadira.sahar@healthedge.com", ADO_PAT),
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"⚠️ GET failed ({attempt}/{MAX_RETRIES}): {e}")
            time.sleep(RETRY_DELAY * attempt)
    return None

def safe_post(url, payload):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(
                url,
                headers=zephyr_headers(),
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"❌ POST failed ({attempt}/{MAX_RETRIES}): {e}")
            time.sleep(RETRY_DELAY * attempt)
    return None


# =====================================================
# ADO FETCHERS
# =====================================================

def get_ado_test_suites(plan_id):
    url = f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/test/plans/{plan_id}/suites"
    return safe_get(url)["value"]


# =====================================================
# SUITE MAP
# =====================================================

def build_suite_map(suites):
    return {
        int(s["id"]): {
            "id": int(s["id"]),
            "name": s["name"],
            "parentId": int(s["parent"]["id"]) if s.get("parent") else None,
        }
        for s in suites
    }


# =====================================================
# FOLDER CREATION LOGIC (UNCHANGED)
# =====================================================

def ensure_folder(suite_id, suite_map):
    suite = suite_map[suite_id]

    parent_id = (
        ensure_folder(suite["parentId"], suite_map)
        if suite["parentId"]
        else None
    )

    key = f"{parent_id}:{suite['name']}"

    if key in state["folders"]:
        return state["folders"][key]

    print(f"📂 Creating folder '{suite['name']}'")

    folder = safe_post(
        f"{ZEPHYR_BASE_URL}/folders",
        {
            "projectKey": JIRA_PROJECT_KEY,
            "name": suite["name"],
            "folderType": "TEST_CYCLE",
            "parentId": parent_id,
        },
    )

    if folder:
        state["folders"][key] = folder["id"]
        save_state()
        time.sleep(0.08) 
        return folder["id"]

    return None


# =====================================================
# MAIN
# =====================================================

def create_all_folders():
    print("🚀 Creating Zephyr folders from ADO suites")

    suites = get_ado_test_suites(ADO_TEST_PLAN_ID)
    suite_map = build_suite_map(suites)

    for suite in suites:
        if not suite.get("parent"):
            continue

        suite_id = int(suite["id"])
        ensure_folder(suite_id, suite_map)

    print("✅ Folder creation complete")


if __name__ == "__main__":
    create_all_folders()