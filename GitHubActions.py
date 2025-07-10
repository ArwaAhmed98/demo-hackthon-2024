import subprocess
import time
import requests
import os
import yaml
import base64
import re
import openai
import subprocess

# Static variables
GITHUB_API_URL = "https://api.github.com"
REPO_OWNER = "ArwaAhmed98"
REPO_NAME = "demo-hackthon-2024"
WORKFLOW_FILE_PATH = ".github/workflows/HelloWorld.yml"
GITHUB_TOKEN = "" 
BACKUP_DIRECTORY = "." # current dir
BUILD_POLL_INTERVAL = 10  # Time in seconds between status checks
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")


# Initialize OpenAI API key
openai.api_key = CHATGPT_API_KEY

def trigger_github_actions_workflow(repo_owner, repo_name, workflow_file_path, github_token):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    workflow_id = os.path.basename(workflow_file_path)
    response = requests.post(
        f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/actions/workflows/{workflow_id}/dispatches",
        headers=headers,
        json={"ref": "main"}  # Assuming 'main' branch. Change if needed.
    )
    if response.status_code == 204:
        print("Workflow triggered successfully")
        return True, None
    else:
        print(f"Failed to trigger workflow: {response.text}")
        return False, None

def get_workflow_run(repo_owner, repo_name, github_token):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.get(
        f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/actions/runs",
        headers=headers
    )
    if response.status_code == 200:
        runs = response.json().get("workflow_runs", [])
        if runs:
            return runs[0]
    return None

def wait_for_workflow_to_finish(repo_owner, repo_name, run_id, github_token):
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    while True:
        response = requests.get(
            f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}",
            headers=headers
        )
        if response.status_code == 200:
            run = response.json()
            status = run.get("status")
            conclusion = run.get("conclusion")
            print(f"Workflow status: {status}, conclusion: {conclusion}")
            if status == "completed":
                return conclusion
        else:
            print(f"Failed to get workflow status: {response.text}")
        time.sleep(BUILD_POLL_INTERVAL)

def save_initial_workflow_config(repo_owner, repo_name, workflow_file_path, backup_directory):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.raw"
    }
    response = requests.get(
        f"{GITHUB_API_URL}/repos/{repo_owner}/{repo_name}/contents/{workflow_file_path}",
        headers=headers
    )
    if response.status_code == 200:
        try:
            response_json = response.json()
            content = response_json.get("content", "")
            if not content:
                print("Error: No content found in the response")
                return None
            initial_config_path = os.path.join(backup_directory, f"initial_config_{os.path.basename(workflow_file_path)}")
            with open(initial_config_path, 'w') as f:
                f.write(base64.b64decode(content).decode('utf-8'))
            print(f"Initial workflow config saved to {initial_config_path}")
            return initial_config_path
        except ValueError:
            response_text = response.text
            print("Error: Failed to decode JSON response, processing as text/YAML")
            print(f"Response text: {response_text}")
            if not response_text:
                print("Error: Response is empty")
                return None
            try:
                yaml_content = yaml.safe_load(response_text)
                initial_config_path = os.path.join(backup_directory, f"initial_config_{os.path.basename(workflow_file_path)}")
                with open(initial_config_path, 'w') as f:
                    yaml.dump(yaml_content, f)
                print(f"Initial workflow config saved to {initial_config_path}")
                return initial_config_path
            except yaml.YAMLError as e:
                print("Error: Failed to parse response as YAML")
                print(f"Response content: {response_text}")
                return None
    else:
        print(f"Failed to save initial workflow config: {response.text}")
        return None

def use_chatgpt_to_correct_workflow(workflow_content):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "user",
                "content": f"Here is a GitHub Actions workflow file that is failing:\n\n{workflow_content}\n\nPlease provide a corrected version of this file."
            }
        ]
    )
    corrected_workflow = response['choices'][0]['message']['content']
    return corrected_workflow

def RaisePR(GITHUB_TOKEN):
    headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
    }

    data = {
        "title": "AI Fix feature",
        "body": "This PR implements the authentication feature using AIOps",
        "head": "auth-feature",
        "base": "main"
    }

    response = requests.post("https://api.github.com/repos/ArwaAhmed98/demo-hackthon-2024/pulls", headers=headers, json=data)

    if response.status_code == 201:
        print("Pull request created successfully.")
    else:
        print(f"Failed to create pull request. Status code: {response.status_code}")
        print(response.json())
        

def main():
    success, _ = trigger_github_actions_workflow(REPO_OWNER, REPO_NAME, WORKFLOW_FILE_PATH, GITHUB_TOKEN)
    if success:
        print("Waiting for GitHub Actions workflow to finish...")
        initial_workflow_config_path = save_initial_workflow_config(REPO_OWNER, REPO_NAME, WORKFLOW_FILE_PATH, BACKUP_DIRECTORY)
        
        if initial_workflow_config_path is None:
            print("Failed to save initial workflow config. Exiting.")
            return

        workflow_run = get_workflow_run(REPO_OWNER, REPO_NAME, GITHUB_TOKEN)
        if workflow_run:
            run_id = workflow_run.get("id")
            initial_conclusion = wait_for_workflow_to_finish(REPO_OWNER, REPO_NAME, run_id, GITHUB_TOKEN)

            if initial_conclusion in ["failure", "startup_failure"]:
                print("Initial workflow run failed. Attempting to correct the workflow with ChatGPT...")
                
                with open(initial_workflow_config_path, 'r') as file:
                    workflow_content = file.read()
                
                corrected_workflow = use_chatgpt_to_correct_workflow(workflow_content)

                corrected_workflow_path = os.path.join(BACKUP_DIRECTORY, "corrected_workflow.yml")
                with open(corrected_workflow_path, 'w') as file:
                    file.write(corrected_workflow)

                print(f"Corrected workflow file saved to {corrected_workflow_path}. No further actions taken.")
                # start commiting to git
                command=(f'git clone https://{GITHUB_TOKEN}@github.com/ArwaAhmed98/demo-hackthon-2024.git')
                os.system(command)
                command=("cd ./demo-hackthon-2024 && \
                git checkout auth-feature && \
                cp ../corrected_workflow.yml ./.github/workflows/helloworld-corrected.yml && \
                git add . && git commit -m 'Fix Commit' && git push")
                os.system(command)
                RaisePR(GITHUB_TOKEN)

            else:
                print("Initial workflow run succeeded.")
        else:
            print("Failed to get workflow run details.")
    else:
        print("Failed to trigger initial GitHub Actions workflow.")


        
if __name__ == "__main__":
    main()
