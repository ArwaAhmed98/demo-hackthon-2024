#!/usr/bin/env python3
"""
LLM-driven GitHub Actions workflow fixer.

* Triggers the workflow
* If it fails, asks a self-hosted Llama-3 to patch the YAML
* Commits the fix on a new branch and opens a PR
"""

import subprocess
import time
import requests
import os
import base64
import re
import json
import shutil                 # ▲ NEW: replace shell `cp` with shutil.copy2

# ───────────── Static configuration ─────────────
GITHUB_API_URL      = "https://api.github.com"
REPO_OWNER          = "ArwaAhmed98"
REPO_NAME           = "demo-hackthon-2024"
WORKFLOW_FILE_PATH  = ".github/workflows/HelloWorld.yml"
GITHUB_TOKEN        = os.getenv("GHE_TOKEN")            # export GHE_TOKEN=...
BACKUP_DIRECTORY    = "/Users/abdelhalima3/Downloads/Hackthon"
BUILD_POLL_INTERVAL = 10                                # seconds

# ── Self-hosted LLM details ──────────────────────
CUSTOM_LLM_BASE_URL = "http://3.236.245.215"            # no trailing slash
CUSTOM_LLM_MODEL    = "llama3"
CUSTOM_LLM_TOKEN    = os.getenv("LLM_TOKEN")

# ────────── GitHub Actions helpers ───────────────
def trigger_github_actions_workflow(repo_owner, repo_name, workflow_file_path, github_token) -> bool:
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    workflow_id = os.path.basename(workflow_file_path)
    resp = requests.post(
        f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/actions/workflows/{workflow_id}/dispatches",
        headers=headers,
        json={"ref": "main"}
    )
    if resp.status_code == 204:
        print("✅ Workflow triggered")
        return True
    print(f"❌ Failed to trigger workflow: {resp.text}")
    return False


def get_workflow_run(repo_owner, repo_name, github_token):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    resp = requests.get(f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/actions/runs", headers=headers)
    if resp.status_code == 200:
        runs = resp.json().get("workflow_runs", [])
        return runs[0] if runs else None
    return None


def wait_for_workflow_to_finish(repo_owner, repo_name, run_id, github_token):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    while True:
        resp = requests.get(
            f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}",
            headers=headers,
        )
        if resp.status_code == 200:
            run = resp.json()
            status = run.get("status")
            conclusion = run.get("conclusion")
            print(f"⏳ Workflow status: {status}, conclusion: {conclusion}")
            if status == "completed":
                return conclusion
        else:
            print(f"❌ Error getting status: {resp.text}")
        time.sleep(BUILD_POLL_INTERVAL)


def save_initial_workflow_config(repo_owner, repo_name, workflow_file_path, backup_directory):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    url = f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/contents/{workflow_file_path}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch workflow file: {resp.status_code} – {resp.text}")
        return None

    try:
        content_b64 = resp.json().get("content", "")
        if not content_b64:
            print("❌ No content found in GitHub response.")
            return None
        decoded = base64.b64decode(content_b64).decode("utf-8")
        backup_path = os.path.join(
            backup_directory,
            f"initial_config_{os.path.basename(workflow_file_path)}",
        )
        with open(backup_path, "w") as fh:
            fh.write(decoded)
        print(f"✅ Workflow saved to: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"❌ Failed to decode workflow content: {e}")
        return None


# ───────────── ✨ LLM integration ✨ ──────────────
def use_llama3_to_correct_workflow(workflow_content: str) -> str:
    """
    Sends the faulty workflow to the self-hosted Llama-3 model and
    returns the corrected YAML.
    """
    url = f"{CUSTOM_LLM_BASE_URL.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if CUSTOM_LLM_TOKEN:
        headers["Authorization"] = f"Bearer {CUSTOM_LLM_TOKEN}"

    payload = {
        "model": CUSTOM_LLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Here is a GitHub Actions workflow file that is failing:\n\n"
                    f"{workflow_content}\n\n"
                    "Please provide a corrected version of this file, ONLY provide the code no additional comments."
                ),
            }
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"LLM request failed: {resp.status_code} – {resp.text}")

    try:
        raw_reply = resp.json()["choices"][0]["message"]["content"]
        # strip ```yaml ... ``` fences if present
        yaml_only = re.sub(
            r"^\s*```(?:ya?ml)?\s*\n|\n```?\s*$",
            "",
            raw_reply.strip(),
            flags=re.IGNORECASE | re.MULTILINE,
        )
        return yaml_only
    except (KeyError, ValueError) as exc:
        raise RuntimeError(f"Unexpected LLM response:\n{resp.text}") from exc


# ───────────── GitHub PR helper ────────────────
def raise_pr(github_token):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": "AI-generated workflow fix",
        "body": "This PR patches the workflow using an LLM-generated correction.",
        "head": "auth-feature",
        "base": "main",
    }
    resp = requests.post(
        f"{GITHUB_API_URL}/repos/{REPO_OWNER}/{REPO_NAME}/pulls",
        headers=headers,
        json=data,
    )
    if resp.status_code == 201:
        print("✅ Pull request created.")
    else:
        print(f"❌ PR creation failed ({resp.status_code}): {resp.text}")


# ───────────── Main orchestration ──────────────
def main():
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN is missing; export GHE_TOKEN first.")
        return

    if not trigger_github_actions_workflow(
        REPO_OWNER, REPO_NAME, WORKFLOW_FILE_PATH, GITHUB_TOKEN
    ):
        return

    print("🔄 Waiting for initial run to finish…")
    initial_cfg_path = save_initial_workflow_config(
        REPO_OWNER, REPO_NAME, WORKFLOW_FILE_PATH, BACKUP_DIRECTORY
    )
    if not initial_cfg_path:
        return

    run = get_workflow_run(REPO_OWNER, REPO_NAME, GITHUB_TOKEN)
    if not run:
        print("❌ Could not fetch workflow run metadata.")
        return

    conclusion = wait_for_workflow_to_finish(
        REPO_OWNER, REPO_NAME, run["id"], GITHUB_TOKEN
    )
    if conclusion not in {"failure", "startup_failure"}:
        print("🎉 Workflow succeeded; no fix needed.")
        return

    print("⚙️  Workflow failed – generating fix via Llama-3 …")
    faulty_yaml = open(initial_cfg_path).read()
    corrected_yaml = use_llama3_to_correct_workflow(faulty_yaml)

    corrected_path = os.path.join(BACKUP_DIRECTORY, "corrected_workflow.yml")
    with open(corrected_path, "w") as fh:
        fh.write(corrected_yaml)
    print(f"💾 Corrected workflow written ➜ {corrected_path}")

    # ── Commit fix on "auth-feature" branch ──
    subprocess.run(
        [
            "git",
            "clone",
            f"https://{GITHUB_TOKEN}@github.com/{REPO_OWNER}/{REPO_NAME}.git",
        ],
        check=True,
    )
    repo_dir = os.path.join(os.getcwd(), REPO_NAME)
    subprocess.run(["git", "checkout", "-B", "auth-feature"], cwd=repo_dir, check=True)

    # ▲ Copy the YAML *into* the repo and overwrite the original
    dest_relative = WORKFLOW_FILE_PATH          # .github/workflows/HelloWorld.yml
    dest_path = os.path.join(repo_dir, dest_relative)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy2(corrected_path, dest_path)

    # ▲ Stage & commit inside the repo
    subprocess.run(["git", "add", dest_relative], cwd=repo_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: auto-generated workflow patch"],
        cwd=repo_dir,
        check=True,
    )
    subprocess.run(["git", "push", "-u", "origin", "auth-feature"], cwd=repo_dir, check=True)

    # ── Open PR ──
    raise_pr(GITHUB_TOKEN)


if __name__ == "__main__":
    main()
