import argparse
import os
import github
import requests

def get_latest_run_summary(repo, workflow_run_id):
    latest_run = repo.get_workflow_run(workflow_run_id)
    # BUG 1: This loop just iterates through all jobs but only keeps the last one
    # If there are no jobs, 'job' will be undefined
    # FIX: Add error handling and ensure we have a valid job
    job = None
    try:
        jobs = list(latest_run.jobs())
        if jobs:
            job = jobs[-1]  # Get the last job (assuming that's what was intended)
        else:
            return "No jobs found in the workflow run."
    except Exception as e:
        return f"Error getting workflow jobs: {str(e)}"
    
    # BUG 2: logs_url might be a property, not a method
    # FIX: Use as property and add error handling
    try:
        # BUG 3: No error handling for HTTP request
        # FIX: Add try/except and validate response
        r = requests.get(job.logs_url)
        r.raise_for_status()  # Raises exception for 4XX/5XX responses
    except Exception as e:
        return f"Error fetching logs: {str(e)}"
        
    summary = ""
    in_summary = False
    for line in r.text.splitlines():
        line = line.strip()
        if "###START-OF-SUMMARY###" in line:
            in_summary = True
            head_len = len(line.split("###START-OF-SUMMARY###")[0])
            continue
        if "###END-OF-SUMMARY###" in line:
            in_summary = False
            break
        if in_summary:
            line = line[head_len:]
            summary += line + "\n"
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Lint staged recipes.')
    parser.add_argument('--head-repo-owner', type=str, required=True, help='the head repo owner')
    parser.add_argument('--workflow-run-id', type=int, required=True, help='the ID of the workflor run')
    parser.add_argument('--head-sha', type=str, required=True, help='the head SHA of the PR')
    args = parser.parse_args()
    
    gh = github.Github(auth=github.Auth.Token(os.environ["GH_TOKEN"]))
    head_repo = gh.get_repo(f"{args.head_repo_owner}/staged-recipes")
    base_repo = gh.get_repo("conda-forge/staged-recipes")
    
    summary = get_latest_run_summary(base_repo, args.workflow_run_id)
    if summary:
        print(summary)
        commit = head_repo.get_commit(args.head_sha)
        pr = None
        
        # BUG 4: commit.get_pulls() might fail or return nothing
        # FIX: Add error handling
        try:
            for _pr in commit.get_pulls():
                if _pr.base.repo.full_name == base_repo.full_name:
                    pr = _pr
                    break
        except Exception as e:
            print(f"Error fetching PRs from commit: {str(e)}")
                
        if pr is None:
            # for reasons I do not follow, sometimes the head commit API
            # to get pull requests does not return the PR.
            # So we try looking at PRs from base repo and find the same
            # sha+head repo but limit the search since staged-recipes
            # gets tons of PRs.
            max_tries = 50
            num_tries = 0
            try:
                for _pr in base_repo.get_pulls():
                    if (
                        _pr.head.sha == args.head_sha
                        and _pr.head.repo.full_name == head_repo.full_name
                    ):
                        pr = _pr
                        break
                    num_tries += 1
                    if num_tries == max_tries:
                        break
            except Exception as e:
                print(f"Error searching PRs from base repo: {str(e)}")
                    
        if pr is not None:
            comment = None
            try:
                for _comment in pr.get_issue_comments():
                    if "Hi! This is the staged-recipes linter" in _comment.body:
                        comment = _comment
                        break
            except Exception as e:
                print(f"Error fetching comments: {str(e)}")
                    
            if comment:
                if comment.body != summary:
                    # BUG 5: No check if summary has content before accessing first line
                    # FIX: Add validation before splitting
                    curr_fline = comment.body.splitlines()[0].strip() if comment.body else ""
                    new_fl = summary.splitlines()[0].strip() if summary.splitlines() else ""
                    if curr_fline == new_fl:
                        try:
                            comment.edit(summary)
                            print("Updated existing comment")
                        except Exception as e:
                            print(f"Error updating comment: {str(e)}")
                    else:
                        try:
                            pr.create_issue_comment(summary)
                            print("Created new comment (first line different)")
                        except Exception as e:
                            print(f"Error creating new comment: {str(e)}")
            else:
                try:
                    pr.create_issue_comment(summary)
                    print("Created new comment (no existing comment)")
                except Exception as e:
                    print(f"Error creating comment: {str(e)}")
        else:
            print("No PR found for the given commit. No comment being made!")
