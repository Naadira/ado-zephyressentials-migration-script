import requests
import xml.etree.ElementTree as ET
import time
import json
import os
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup
import csv
# =====================================================
# CONFIGURATION
# =====================================================

ADO_ORG = "HESource"
ADO_PROJECT = "Source"
ADO_PAT = ""

ADO_TEST_PLAN_ID = 605030

ZEPHYR_BASE_URL = "https://prod-api.zephyr4jiracloud.com/v2"
ZEPHYR_API_TOKEN = ""
JIRA_PROJECT_KEY = "ATC"
JIRA_PROJECT_ID = 598251

FOLDER_JSON = "plan_migration_state.json"

# ===== ADD THIS HERE =====
TESTCASE_KEY_MAP_FILE = "testcase_key_map.json"

TARGET_SUITES = {
    772547

    # 605060


}

STATUS_MAP = {
    "Passed": "PASS", "passed": "PASS",
    "Failed": "FAIL", "failed": "FAIL",
    "Blocked": "BLOCKED", "blocked": "BLOCKED",
    "Not run": "NOT EXECUTED",
    "Not Run": "NOT EXECUTED"
}

PRIORITY_MAP = {
    1: "Highest",
    2: "High",
    3: "Medium",
    4: "Low",
    5: "Lowest"
}

CYCLE_STATUS_MAP = {
    "New": "New",
    "In Refinement": "In Refinement",
    "Ready": "Ready",
    "Blocked": "Blocked",
    "In Development": "In Development",
    "Development Complete" :"Development Complete",
    "In Test" : "In Test",
    "Test Complete" : "Test Complete",
    "Closed": "Closed"
}

TESTCASE_STATUS_MAP = {
    "Design": "Design",
    "Ready": "Ready",
    "In Progress": "In Progress",
    "Closed": "Closed",
    "Blocked": "Blocked",
    "Removed": "Removed"
}

# =====================================================
# EXCEL LOGGING STRUCTURE
# =====================================================

cycle_rows = []
testcase_rows = []
execution_rows = []
# =====================================================
# RETRY WRAPPER
# =====================================================

def request_with_retry(method, url, **kwargs):
    retries = 4
    backoff = 2

    for attempt in range(1, retries + 1):
        try:
            print(f"→ {method.upper()} {url} (attempt {attempt})")
            r = requests.request(method, url, timeout=60, **kwargs)

            if r.status_code >= 500:
                raise Exception(f"Server error {r.status_code}")

            r.raise_for_status()
            if r.text.strip():
                return r.json()
            return {}

        except Exception as e:
            print(f"   ⚠ Retry {attempt} failed:", e)
            if attempt == retries:
                print("   ❌ Giving up")
                raise
            time.sleep(backoff ** attempt)

# =====================================================
# STATE MANAGEMENT
# =====================================================

def load_state():
    if not os.path.exists(FOLDER_JSON):
        return {
            "folders": {},
            "cycles": {},
            "testcases": {},
            "executions": {},
            "last_suite": None,
            "last_tc": None
        }

    with open(FOLDER_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_state():
    with open(FOLDER_JSON, "w", encoding="utf-8") as f:
        json.dump(STATE, f, indent=2)

# ===== ADD THIS HERE =====

def load_testcase_key_map():
    if not os.path.exists(TESTCASE_KEY_MAP_FILE):
        return {}
    with open(TESTCASE_KEY_MAP_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_testcase_key_map():
    with open(TESTCASE_KEY_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(TESTCASE_KEY_MAP, f, indent=2)

# =====================================================
# USER MAPPING (ADO → JIRA)
# =====================================================

USER_MAP_FILE = "ado_jira_user_map.csv"

def load_user_map():
    mapping = {}

    if not os.path.exists(USER_MAP_FILE):
        print("⚠ No user mapping CSV found")
        return mapping

    with open(USER_MAP_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ado = row["ADO User"].strip()
            jira = row["Jira Account id"].strip()
            mapping[ado] = jira

    print("✔ Loaded user mappings:", len(mapping))
    return mapping


ADO_TO_JIRA_USER = load_user_map()
# =====================================================
# HELPERS
# =====================================================

def zephyr_headers():
    return {
        "Authorization": f"Bearer {ZEPHYR_API_TOKEN}",
        "Content-Type": "application/json"
    }

def clean_html(text):
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(" ").strip()

def safe_get(url):
    return request_with_retry(
        "get",
        url,
        auth=HTTPBasicAuth("", ADO_PAT)
    )
def safe_get_zephyr(url):
    return request_with_retry(
        "get",
        url,
        headers=zephyr_headers()
    )

def safe_post(url, payload):
    return request_with_retry(
        "post",
        url,
        headers=zephyr_headers(),
        json=payload
    )

def safe_put(url, payload):
    return request_with_retry(
        "put",
        url,
        headers=zephyr_headers(),
        json=payload
    )

# =====================================================
# LOAD FOLDER LOOKUP
# =====================================================

def load_folder_lookup():
    print("\nLoading folder lookup...")
    with open(FOLDER_JSON, encoding="utf-8") as f:
        data = json.load(f)["folders"]

    lookup = {}
    for key, val in data.items():
        suite_name = key.split(":",1)[1]
        lookup[suite_name] = val

    print("✔ Folder mappings loaded:", len(lookup))
    return lookup

STATE = load_state()
FOLDER_LOOKUP = load_folder_lookup()

# ===== ADD THIS HERE =====
TESTCASE_KEY_MAP = load_testcase_key_map()

# =====================================================
# ADO FETCHERS
# =====================================================

def get_suites():
    print("\nFetching ADO suites...")
    url=f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/test/plans/{ADO_TEST_PLAN_ID}/suites"
    return safe_get(url)["value"]

def get_testcases(suite_id):
    print(f"Fetching testcases for suite {suite_id}")
    url=f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/test/plans/{ADO_TEST_PLAN_ID}/suites/{suite_id}/testcases"
    return safe_get(url).get("value", [])

def get_execution_points(suite_id):
    print(f"Fetching execution points for suite {suite_id}")
    url=f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/testplan/Plans/{ADO_TEST_PLAN_ID}/Suites/{suite_id}/TestPoint"
    return safe_get(url).get("value", [])

def get_testcase(tc_id):
    url=f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/wit/workitems/{tc_id}"
    return safe_get(url)

def get_step_results(run_id, result_id):
    url=f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis/test/Runs/{run_id}/Results/{result_id}/Iterations"
    data=safe_get(url).get("value",[])
    steps=[]
    for it in data:
        for s in it.get("actionResults",[]):
            steps.append(s)
    print("   Step results:", len(steps))
    return steps

# =====================================================
# STEP PARSING
# =====================================================

def parse_steps(xml):
    if not xml:
        return []

    root=ET.fromstring(xml)
    out=[]
    i=1

    for step in root.findall(".//step"):
        texts=[clean_html(x.text) for x in step.findall("parameterizedString")]
        if not any(texts):
            continue

        out.append({
            "description": str(i),
            "testData": texts[0] if len(texts)>0 else "",
            "expectedResult": texts[1] if len(texts)>1 else ""
        })
        i+=1

    print("   Parsed steps:", len(out))
    return out

# =====================================================
# LOGGING HELPERS
# =====================================================

def log_cycle(name, key, status, owner):
    print("\n================ CYCLE LOG ================")
    print("Cycle Name      :", name)
    print("Cycle Key       :", key)
    print("Cycle Status    :", status)
    print("Cycle Owner     :", owner)
    print("===========================================\n")

def log_testcase(ado_id, key, status, priority, owner):
    print("\n================ TESTCASE LOG ================")
    print("ADO ID          :", ado_id)
    print("Zephyr Key      :", key)
    print("Status          :", status)
    print("Priority        :", priority)
    print("Owner           :", owner)
    print("=============================================\n")

def log_execution(tc_key, cycle_key, status, executed_by, assigned_to, environment):
    print("\n================ EXECUTION LOG ================")
    print("TestCase        :", tc_key)
    print("Cycle           :", cycle_key)
    print("Execution Status:", status)
    print("Executed By     :", executed_by)
    print("Assigned To     :", assigned_to)
    print("Environment     :", environment)
    print("===============================================\n")

# =====================================================
# ZEPHYR OPS
# =====================================================

def create_cycle(name, folder_id):

    # --------------------------------
    # Extract ADO WorkItem ID
    # --------------------------------
    ado_wi_id = None
    if ":" in name:
        candidate = name.split(":", 1)[0].strip()
        if candidate.isdigit():
            ado_wi_id = candidate

    ado_state = None
    zephyr_status = None   # Initialize as None
    owner = None
    created = None
    closed = None

    # --------------------------------
    # Fetch ADO fields FIRST
    # --------------------------------
    if ado_wi_id:
        wi = get_testcase(ado_wi_id)
        f = wi["fields"]

        ado_state = f.get("System.State")
        zephyr_status = CYCLE_STATUS_MAP.get(ado_state)  # Only map if exists

        ado_created_user = f.get("System.CreatedBy", {}).get("uniqueName")
        owner = ADO_TO_JIRA_USER.get(ado_created_user)

        created = f.get("System.CreatedDate")
        closed = f.get("Microsoft.VSTS.Common.ClosedDate")

    # --------------------------------
    # If no mapping found, fallback to existing or default
    # --------------------------------
    if not zephyr_status:
        if name in STATE["cycles"]:
            zephyr_status = STATE["cycles"][name].get("status")
        else:
            zephyr_status = "New"

    print("ADO Cycle State:", ado_state)
    print("Mapped Zephyr Status:", zephyr_status)

    # =====================================================
    # ⭐ CREATE OR REUSE CYCLE
    # =====================================================
    if name in STATE["cycles"]:
        # Just reuse existing cycle; do NOT update status again
        print("Cycle exists — reuse:", STATE["cycles"][name]["key"])
        return STATE["cycles"][name]["key"]

    # =====================================================
    # ⭐ CREATE NEW CYCLE
    # =====================================================
    payload = {
        "projectKey": JIRA_PROJECT_KEY,
        "name": name,
        "folderId": folder_id,
        "statusName": zephyr_status
    }

    if owner:
        payload["ownerId"] = owner

    if created:
        payload["plannedStartDate"] = created

    if closed:
        payload["plannedEndDate"] = closed

    payload["description"] = f"Migrated from ADO WI {ado_wi_id}"

    print("\n===== FINAL CYCLE PAYLOAD =====")
    print(json.dumps(payload, indent=2))

    cycle = safe_post(
        f"{ZEPHYR_BASE_URL}/testcycles",
        payload
    )

    # ⭐ Store status also
    STATE["cycles"][name] = {
        "key": cycle["key"],
        "id": cycle["id"],
        "status": zephyr_status
    }
    save_state()

    print("✔ Cycle Created:", cycle["key"])

    # ===== ADD THIS =====
    cycle_rows.append({
        "Cycle_Key": cycle["key"],
        "Cycle_Name": name,
        "Status": zephyr_status,
        "Owner": owner,
        "Created_Date": created,
        "Closed_Date": closed
    })

    log_cycle(
    name,
    cycle["key"],
    zephyr_status,
    owner)

    return cycle["key"]


def create_testcase(ado_id, title, desc, steps, owner_id=None, status_name=None,
                    priority_name=None):

    # ---------- Reuse if already migrated ----------
    if ado_id in STATE["testcases"]:
        print("   ✔ Already exists — reuse:", STATE["testcases"][ado_id]["key"])
        return STATE["testcases"][ado_id]["key"]

    print("Creating testcase:", title[:70])

    payload = {
        "projectKey": JIRA_PROJECT_KEY,
        "name": title,
        "objective": desc
    }

    if status_name:
        payload["statusName"] = status_name

    if priority_name:
        payload["priorityName"] = priority_name

    if owner_id:
        payload["ownerId"] = owner_id

    tc = safe_post(
        f"{ZEPHYR_BASE_URL}/testcases",
        payload
    )

    # Upload steps
    if steps:
        safe_post(
            f"{ZEPHYR_BASE_URL}/testcases/{tc['key']}/teststeps",
            {"mode": "OVERWRITE", "items": [{"inline": s} for s in steps]}
        )

    # ---------- STORE EXACT STRUCTURE ----------
    STATE["testcases"][ado_id] = {
        "key": tc["key"],
        "title": title
    }
    save_state()

    # ===== ADD THIS HERE =====
    TESTCASE_KEY_MAP[ado_id] = tc["key"]
    save_testcase_key_map()

    log_testcase(
        ado_id,
        tc["key"],
        status_name,
        priority_name,
        owner_id)
    # ===== ADD THIS =====
    testcase_rows.append({
        "ADO_TestCase_ID": ado_id,
        "TestCase_Key": tc["key"],
        "Title": title,
        "Status": status_name,
        "Priority": priority_name,
        "Owner": owner_id
    })

    print("   ✔ Stored mapping:", ado_id, "→", tc["key"])

    return tc["key"]


def create_execution(tc_key, cycle_key, status, step_results, executed_by, assigned_to, environment=None):

    exec_id = f"{tc_key}|{cycle_key}"
    print("Execution status:"+status)
    if exec_id in STATE["executions"]:
        print("Execution exists — skip")
        return

    payload={
        "projectKey":JIRA_PROJECT_KEY,
        "testCaseKey":tc_key,
        "testCycleKey":cycle_key,
        "statusName":status,
        "testScriptResults":[
            {"statusName":STATUS_MAP.get(s.get("outcome"),"NOT EXECUTED")}
            for s in step_results
        ]
    }
    print("Payload:",payload)
    if environment:
        payload["environmentName"] = environment

    # ---------- Inject executedBy ----------
    if executed_by:
        payload["executedById"] = executed_by

    if assigned_to:
        payload["assignedToId"] = assigned_to

    safe_post(f"{ZEPHYR_BASE_URL}/testexecutions",payload)

    STATE["executions"][exec_id] = status

    # ===== ADD THIS =====
    execution_rows.append({
        "Execution_ID": exec_id,
        "TestCase_Key": tc_key,
        "Cycle_Key": cycle_key,
        "Status": status,
        "Executed_By": executed_by,
        "Assigned_To": assigned_to,
        "Environment": environment
    })
    save_state()

    log_execution(
    tc_key,
    cycle_key,
    status,
    executed_by,
    assigned_to,
    environment)
 
def update_cycle(cycle_id,payload):
    
    # safe_put(f"{ZEPHYR_BASE_URL}/testcycles/{cycle_id}",payload)
    safe_put(f"{ZEPHYR_BASE_URL}/testcycles/{cycle_id}",payload)
    return

# =====================================================
# MAIN
# =====================================================

def run():
    suites = get_suites()

    for s in suites:
        sid = int(s["id"])
        name = s["name"]

        if sid not in TARGET_SUITES:
            continue

        print("\n==============================")
        print("Processing Suite:", sid, name)
        print("==============================")

        # -------- FETCH TESTCASES FIRST --------
        tcs = get_testcases(sid)

        if not tcs:
            print("❌ No testcases in suite — skipping cycle creation")
            continue

        # Check if anything new to migrate
        new_cases = [
            t for t in tcs
            if str(t["testCase"]["id"]) not in STATE["testcases"]
        ]

        if not new_cases:
            print("✔ All testcases already migrated — skipping cycle")
            continue

        print("Total testcases:", len(tcs))
        print("New testcases:", len(new_cases))

        # -------- NOW resolve folder --------
        folder_id = FOLDER_LOOKUP.get(name)
        if not folder_id:
            print("Folder missing — skip")
            continue

        # -------- CREATE CYCLE ONLY NOW --------
        cycle_key = create_cycle(name, folder_id)
        cycle_payload = safe_get_zephyr(f"{ZEPHYR_BASE_URL}/testcycles/{cycle_key}")

        # -------- Fetch execution points --------
        points = get_execution_points(sid)
        point_map = {str(p["testCaseReference"]["id"]): p for p in points}

        for t in tcs:
            tc_id = str(t["testCase"]["id"])
            print("\n--- TC", tc_id, "---")

            ado_tc = get_testcase(tc_id)
            fields = ado_tc["fields"]

            steps = parse_steps(fields.get("Microsoft.VSTS.TCM.Steps"))

            # OWNER
            ado_owner = fields.get("System.CreatedBy", {}).get("uniqueName")
            jira_owner = ADO_TO_JIRA_USER.get(ado_owner)

            print("👑 Owner (ADO):", ado_owner)
            print("🔗 Jira Owner Map:", jira_owner if jira_owner else "NOT FOUND")

            # STATUS + PRIORITY
            ado_state = fields.get("System.State")
            ado_priority_num = fields.get("Microsoft.VSTS.Common.Priority")

            zephyr_status = TESTCASE_STATUS_MAP.get(ado_state)
            print("Test case status: "+zephyr_status)
            zephyr_priority = PRIORITY_MAP.get(ado_priority_num)

            tc_key = create_testcase(
                tc_id,
                fields["System.Title"],
                clean_html(fields.get("System.Description", "")),
                steps,
                jira_owner,
                status_name=zephyr_status,
                priority_name=zephyr_priority
            )

            exec_rec = point_map.get(tc_id, {})
            res = exec_rec.get("results", {})

            status = STATUS_MAP.get(res.get("outcome"), "NOT EXECUTED")
            run_id = res.get("lastTestRunId")
            result_id = res.get("lastResultId")

            step_res = get_step_results(run_id, result_id) if run_id else []

            # EXECUTED BY
            ado_exec_user = exec_rec.get("tester", {}).get("uniqueName")
            jira_exec_user = ADO_TO_JIRA_USER.get(ado_exec_user)

            print("   👤 Executed By (ADO):", ado_exec_user)
            print("   🔗 Jira Exec Map:", jira_exec_user if jira_exec_user else "NOT FOUND")

            # ASSIGNED TO
            ado_assigned_user = fields.get("System.AssignedTo", {}).get("uniqueName")
            jira_assigned_user = ADO_TO_JIRA_USER.get(ado_assigned_user)

            print("   📌 Assigned To (ADO):", ado_assigned_user)
            print("   🔗 Jira Assign Map:", jira_assigned_user if jira_assigned_user else "NOT FOUND")

            environment = fields.get("System.AreaPath")

            create_execution(tc_key, cycle_key, status, step_res, jira_exec_user, jira_assigned_user, environment=environment)
            update_cycle(cycle_key,cycle_payload)
    # =====================================================
    # SAVE EXCEL FILE
    # =====================================================
    import pandas as pd

    with pd.ExcelWriter("migration_log.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(cycle_rows).to_excel(writer, sheet_name="Cycles", index=False)
        pd.DataFrame(testcase_rows).to_excel(writer, sheet_name="TestCases", index=False)
        pd.DataFrame(execution_rows).to_excel(writer, sheet_name="TestExecutions", index=False)

    print("📄 Excel file generated: migration_log.xlsx")
    print("\n🎉 DONE")

if __name__ == "__main__":
    run()
