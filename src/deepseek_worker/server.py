from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .core import ModelName, generate_patch as generate_patch_core
from .jobs import get_job_manager


INSTRUCTIONS = """This server sends selected code context to DeepSeek and returns an untrusted candidate patch. It never edits files. Only call it after inspecting the repository. Provide the minimum necessary context and an exact allowed_paths list. Never send secrets, credentials, customer data, .env files, or unrelated proprietary content. Review the entire returned patch and run local validation before accepting it."""

mcp = FastMCP(
    "DeepSeek Patch Worker",
    instructions=INSTRUCTIONS,
    json_response=True,
)


@mcp.tool()
def generate_patch(
    task: str,
    file_context: str,
    allowed_paths: list[str],
    constraints: str = "",
    test_failures: str = "",
    model: ModelName = "deepseek-v4-pro",
) -> dict:
    """Generate a validated candidate unified diff; this tool never edits the repository.

    Use deepseek-v4-pro for complex work and deepseek-v4-flash for routine changes.
    file_context should label each supplied file with its repository-relative path.
    allowed_paths is the exact list of files the returned patch may add, edit, or delete.
    On a repair round, send current file contents plus exact test/build failures.
    """
    return generate_patch_core(
        task=task,
        file_context=file_context,
        allowed_paths=allowed_paths,
        constraints=constraints,
        test_failures=test_failures,
        model=model,
    )


@mcp.tool()
def review_patch(
    task: str,
    file_context: str,
    candidate_patch: str,
    allowed_paths: list[str],
    constraints: str = "",
    test_results: str = "",
    model: ModelName = "deepseek-v4-pro",
) -> dict:
    """Review an untrusted candidate patch and return a corrected replacement diff, or an empty patch when no correction is justified."""
    review_task = f"""Act as a strict code reviewer. Review the candidate patch against the task and current files.
Identify correctness, security, compatibility, and test problems. Return a complete corrected replacement patch only when changes are needed; otherwise return an empty patch. State the verdict and findings in summary, assumptions, and risks.

ORIGINAL TASK
{task}

CANDIDATE PATCH
{candidate_patch}
"""
    result = generate_patch_core(
        task=review_task,
        file_context=file_context,
        allowed_paths=allowed_paths,
        constraints=constraints,
        test_failures=test_results,
        model=model,
    )
    result["mode"] = "review"
    return result


@mcp.tool()
def submit_patch_job(
    task: str,
    file_context: str,
    allowed_paths: list[str],
    task_name: str = "",
    constraints: str = "",
    test_failures: str = "",
    model: ModelName = "deepseek-v4-pro",
) -> dict:
    """Submit a long-running streamed patch job and return a local job ID immediately."""
    return get_job_manager().submit(
        task=task,
        file_context=file_context,
        allowed_paths=allowed_paths,
        task_name=task_name,
        constraints=constraints,
        test_failures=test_failures,
        model=model,
    )


@mcp.tool()
def get_patch_job(job_id: str) -> dict:
    """Return persisted status and aggregate stream progress for a background job."""
    return get_job_manager().status(job_id)


@mcp.tool()
def get_patch_result(job_id: str) -> dict:
    """Return a persisted validated result, or the current non-terminal status."""
    return get_job_manager().result(job_id)


@mcp.tool()
def cancel_patch_job(job_id: str) -> dict:
    """Request cooperative cancellation of a background streamed job."""
    return get_job_manager().cancel(job_id)


@mcp.tool()
def get_capabilities() -> dict:
    """Return local worker capabilities without calling DeepSeek."""
    return {
        "worker": "deepseek",
        "version": "0.2.0",
        "tools": [
            "generate_patch", "review_patch", "submit_patch_job", "get_patch_job",
            "get_patch_result", "cancel_patch_job", "get_capabilities"
        ],
        "models": ["deepseek-v4-pro", "deepseek-v4-flash"],
        "writes_files": False,
        "streaming": True,
        "background_jobs": True,
        "max_persisted_result_bytes": 2 * 1024 * 1024,
        "returns": ["patch", "changed_files", "patch_sha256", "tests", "risks", "usage"],
        "display_contract": "Worker returns an untrusted diff; Codex reviews and applies it for native file-change display.",
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
