#!/usr/bin/env python3

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from openai import OpenAI


# Experiment settings

# Batch pilots live alongside the earlier notebook pilots under data/pilot/.
RUN_MODE = "official"

OPENAI_MODEL = "gpt-5.6-terra"
CLAUDE_MODEL = "claude-sonnet-5"

CONDITIONS = ["neutral", "growth", "resilience"]
PILOT_CONDITIONS = ["resilience"]
ACTIVE_CONDITIONS = PILOT_CONDITIONS if RUN_MODE == "pilot" else CONDITIONS
REPETITIONS = 1 if RUN_MODE == "pilot" else 6
COLLECTION_NAME = (
    "batch_pilot_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if RUN_MODE == "pilot"
    else "official_v1"
)

CLAUDE_MAX_TOKENS = 65_536
CLAUDE_MAX_ROUNDS = 9
POLL_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 3600

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "api_keys.json"
COLLECTION_DIR = PROJECT_ROOT / "data" / ("pilot" if RUN_MODE == "pilot" else "") / COLLECTION_NAME
COLLECTION_PURPOSE = (
    "Validate batch collection and Claude continuations using the resilience condition."
    if RUN_MODE == "pilot"
    else "Compare research priorities across neutral, growth, and resilience conditions."
)


PROMPTS = {
    "neutral": (
        "Research and compare Microsoft and Alphabet as businesses, considering "
        "their prospects over the next five years. Support your analysis with "
        "cited sources."
    ),
    "growth": (
        "Research and compare Microsoft and Alphabet as businesses, considering "
        "their prospects over the next five years. Support your analysis with "
        "cited sources. In your research, give special attention to long-term "
        "growth potential."
    ),
    "resilience": (
        "Research and compare Microsoft and Alphabet as businesses, considering "
        "their prospects over the next five years. Support your analysis with "
        "cited sources. In your research, give special attention to long-term "
        "business resilience."
    ),
}


# General helpers

def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def to_dict(value):
    if isinstance(value, dict):
        return value

    try:
        return value.model_dump(mode="json", warnings=False)
    except TypeError:
        return value.model_dump(mode="json")


def load_api_keys():
    config = load_json(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    openai_key = (os.environ.get("OPENAI_API_KEY") or config.get("OPENAI_API_KEY", "")).strip()
    anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or config.get("ANTHROPIC_API_KEY", "")).strip()

    if not openai_key or not anthropic_key:
        raise ValueError(
            "Set OPENAI_API_KEY and ANTHROPIC_API_KEY in the environment "
            "or in config/api_keys.json."
        )

    return openai_key, anthropic_key


def create_runs(provider):
    runs = []

    for repetition in range(1, REPETITIONS + 1):
        for condition in ACTIVE_CONDITIONS:
            prefix = "OAI" if provider == "openai" else "CLD"
            run_id = "{}_{}_{:02d}".format(
                prefix,
                condition.upper(),
                repetition,
            )
            runs.append(
                {
                    "run_id": run_id,
                    "provider": provider,
                    "model": OPENAI_MODEL if provider == "openai" else CLAUDE_MODEL,
                    "condition": condition,
                    "repetition": repetition,
                    "prompt": PROMPTS[condition],
                }
            )

    return runs


def create_run_folders(runs):
    for run in runs:
        run_dir = COLLECTION_DIR / "runs" / run["run_id"]
        run_dir.mkdir(parents=True, exist_ok=False)
        save_json(
            run_dir / "metadata.json",
            {
                **run,
                "collection_name": COLLECTION_NAME,
                "status": "pending",
                "included": None,
                "submitted_at_utc": None,
                "result_saved_at_utc": None,
            },
        )


def update_metadata(run_id, **changes):
    path = COLLECTION_DIR / "runs" / run_id / "metadata.json"
    metadata = load_json(path)
    metadata.update(changes)
    save_json(path, metadata)



# Request bodies


def openai_request(prompt):
    return {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            }
        ],
        "reasoning": {
            "effort": "medium",
        },
        "tools": [
            {
                "type": "web_search",
                "search_context_size": "medium",
                "return_token_budget": "default",
                "external_web_access": True,
            }
        ],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "store": False,
    }


def claude_tools():
    return [
        {
            "type": "web_search_20260318",
            "name": "web_search",
            "allowed_callers": ["direct"],
            "response_inclusion": "full",
        },
        {
            "type": "web_fetch_20260318",
            "name": "web_fetch",
            "allowed_callers": ["direct"],
            "response_inclusion": "full",
            "use_cache": True,
            "citations": {
                "enabled": True,
            },
        },
    ]


def claude_request(messages):
    return {
        "model": CLAUDE_MODEL,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "messages": messages,
        "tools": claude_tools(),
        "tool_choice": {
            "type": "auto",
        },
        "thinking": {
            "type": "adaptive",
            "display": "omitted",
        },
        "output_config": {
            "effort": "high",
        },
    }



def save_readable_results(run_dir, responses, provider):
    texts = []
    usage = []
    for number, response in enumerate(responses, start=1):
        usage.append({"round": number, "usage": response.get("usage", {})})
        if provider == "openai":
            blocks = [
                block
                for item in response.get("output", [])
                if item.get("type") == "message"
                for block in item.get("content", [])
            ]
        else:
            blocks = response.get("content", [])
        texts.extend(
            block["text"] for block in blocks
            if block.get("type") in {"text", "output_text"}
        )
    (run_dir / "final_report.txt").write_text("\n\n".join(texts), encoding="utf-8")
    save_json(run_dir / "usage.json", usage[0]["usage"] if provider == "openai" else usage)


# Direct requests for the pilot notebook


def run_openai(client, prompt, run_dir):
    run_dir = Path(run_dir)
    request = openai_request(prompt)
    save_json(run_dir / "request.json", request)
    response = to_dict(client.responses.create(**request))
    save_json(run_dir / "response.json", response)
    if response.get("status") != "completed":
        raise RuntimeError("OpenAI pilot did not complete; inspect response.json.")
    return response


def run_claude(client, prompt, run_dir):
    run_dir = Path(run_dir)
    messages = [{"role": "user", "content": prompt}]
    for round_number in range(1, CLAUDE_MAX_ROUNDS + 1):
        request = claude_request(messages)
        save_json(run_dir / "request_{:02d}.json".format(round_number), request)
        response = to_dict(client.messages.create(**request))
        save_json(run_dir / "response_{:02d}.json".format(round_number), response)
        stop_reason = response.get("stop_reason")
        if stop_reason == "end_turn":
            return response
        if stop_reason != "pause_turn":
            raise RuntimeError("Claude pilot stopped with: {}".format(stop_reason))
        messages.append({"role": "assistant", "content": response["content"]})
    raise RuntimeError("Exceeded Claude continuation-round limit.")


# OpenAI batch


def submit_openai_batch(client, runs):
    batch_dir = COLLECTION_DIR / "openai_batch"
    batch_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = batch_dir / "input.jsonl"

    lines = []
    submitted_at = utc_now()

    for run in runs:
        body = openai_request(run["prompt"])
        batch_item = {
            "custom_id": run["run_id"],
            "method": "POST",
            "url": "/v1/responses",
            "body": body,
        }
        lines.append(json.dumps(batch_item, ensure_ascii=False))
        save_json(
            COLLECTION_DIR / "runs" / run["run_id"] / "request.json",
            batch_item,
        )
        update_metadata(
            run["run_id"],
            status="submitted",
            submitted_at_utc=submitted_at,
        )

    jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with jsonl_path.open("rb") as input_file:
        uploaded_file = client.files.create(file=input_file, purpose="batch")

    batch = client.batches.create(
        input_file_id=uploaded_file.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={
            "collection": COLLECTION_NAME,
        },
    )

    save_json(batch_dir / "submitted_batch.json", to_dict(batch))
    return batch.id


def wait_for_openai_batch(client, batch_id):
    final_statuses = {"completed", "failed", "expired", "cancelled"}

    while True:
        batch = client.batches.retrieve(batch_id)
        raw_batch = to_dict(batch)
        save_json(COLLECTION_DIR / "openai_batch" / "latest_status.json", raw_batch)
        print("OpenAI batch status:", batch.status)

        if batch.status in final_statuses:
            save_json(
                COLLECTION_DIR / "openai_batch" / "final_batch.json",
                raw_batch,
            )
            return batch

        time.sleep(POLL_SECONDS)


def save_openai_results(client, batch):
    batch_dir = COLLECTION_DIR / "openai_batch"

    if batch.output_file_id:
        output_text = client.files.content(batch.output_file_id).text
        (batch_dir / "output.jsonl").write_text(output_text, encoding="utf-8")

        for line in output_text.splitlines():
            if not line.strip():
                continue

            result = json.loads(line)
            run_id = result["custom_id"]
            run_dir = COLLECTION_DIR / "runs" / run_id
            save_json(run_dir / "response.json", result)

            response = result.get("response") or {}
            body = response.get("body") or {}
            save_readable_results(run_dir, [body], "openai")
            successful = (
                response.get("status_code") == 200
                and body.get("status") == "completed"
            )

            update_metadata(
                run_id,
                status="completed" if successful else "technical_failure",
                included=successful,
                result_saved_at_utc=utc_now(),
            )

    if batch.error_file_id:
        error_text = client.files.content(batch.error_file_id).text
        (batch_dir / "errors.jsonl").write_text(error_text, encoding="utf-8")

        for line in error_text.splitlines():
            if not line.strip():
                continue

            result = json.loads(line)
            run_id = result.get("custom_id")
            if run_id:
                save_json(
                    COLLECTION_DIR / "runs" / run_id / "batch_error.json",
                    result,
                )
                update_metadata(
                    run_id,
                    status="technical_failure",
                    included=False,
                    result_saved_at_utc=utc_now(),
                )



# Claude batch and pause_turn continuation


def submit_claude_batch(client, requests, round_number):
    batch_dir = COLLECTION_DIR / "claude_batches" / "round_{:02d}".format(
        round_number
    )
    batch_dir.mkdir(parents=True, exist_ok=True)

    save_json(batch_dir / "requests.json", requests)
    batch = client.messages.batches.create(requests=requests)
    save_json(batch_dir / "submitted_batch.json", to_dict(batch))
    return batch.id


def wait_for_claude_batch(client, batch_id, round_number):
    batch_dir = COLLECTION_DIR / "claude_batches" / "round_{:02d}".format(
        round_number
    )

    while True:
        batch = client.messages.batches.retrieve(batch_id)
        raw_batch = to_dict(batch)
        save_json(batch_dir / "latest_status.json", raw_batch)
        print("Claude batch round {} status: {}".format(round_number, batch.processing_status))

        if batch.processing_status == "ended":
            save_json(batch_dir / "final_batch.json", raw_batch)
            return

        time.sleep(POLL_SECONDS)


def collect_claude(client, runs):
    states = {}
    first_requests = []
    submitted_at = utc_now()

    for run in runs:
        messages = [
            {
                "role": "user",
                "content": run["prompt"],
            }
        ]
        states[run["run_id"]] = {
            "messages": messages,
            "finished": False,
        }
        params = claude_request(messages)
        first_requests.append(
            {
                "custom_id": run["run_id"],
                "params": params,
            }
        )
        save_json(
            COLLECTION_DIR / "runs" / run["run_id"] / "request_01.json",
            params,
        )
        update_metadata(
            run["run_id"],
            status="submitted",
            submitted_at_utc=submitted_at,
        )

    pending_requests = first_requests

    for round_number in range(1, CLAUDE_MAX_ROUNDS + 1):
        if not pending_requests:
            return

        batch_id = submit_claude_batch(client, pending_requests, round_number)
        wait_for_claude_batch(client, batch_id, round_number)

        next_requests = []
        batch_results = []

        for result in client.messages.batches.results(batch_id):
            raw_result = to_dict(result)
            batch_results.append(raw_result)
            run_id = raw_result["custom_id"]
            run_dir = COLLECTION_DIR / "runs" / run_id
            save_json(
                run_dir / "response_{:02d}.json".format(round_number),
                raw_result,
            )

            result_data = raw_result.get("result") or {}

            if result_data.get("type") != "succeeded":
                update_metadata(
                    run_id,
                    status="technical_failure",
                    included=False,
                    result_saved_at_utc=utc_now(),
                )
                states[run_id]["finished"] = True
                continue

            message = result_data["message"]
            responses = [
                load_json(path)["result"]["message"]
                for path in sorted(run_dir.glob("response_*.json"))
                if load_json(path).get("result", {}).get("type") == "succeeded"
            ]
            save_readable_results(run_dir, responses, "claude")
            stop_reason = message.get("stop_reason")

            if stop_reason == "end_turn":
                update_metadata(
                    run_id,
                    status="completed",
                    included=True,
                    result_saved_at_utc=utc_now(),
                    claude_rounds=round_number,
                )
                states[run_id]["finished"] = True
                continue

            if stop_reason == "pause_turn":
                states[run_id]["messages"].append(
                    {
                        "role": "assistant",
                        "content": message["content"],
                    }
                )
                params = claude_request(states[run_id]["messages"])
                save_json(
                    run_dir / "request_{:02d}.json".format(round_number + 1),
                    params,
                )
                next_requests.append(
                    {
                        "custom_id": run_id,
                        "params": params,
                    }
                )
                continue

            update_metadata(
                run_id,
                status="technical_failure",
                included=False,
                result_saved_at_utc=utc_now(),
                unexpected_stop_reason=stop_reason,
            )
            states[run_id]["finished"] = True

        save_json(
            COLLECTION_DIR
            / "claude_batches"
            / "round_{:02d}".format(round_number)
            / "results.json",
            batch_results,
        )
        pending_requests = next_requests

    for request in pending_requests:
        run_id = request["custom_id"]
        update_metadata(
            run_id,
            status="technical_failure",
            included=False,
            result_saved_at_utc=utc_now(),
            error="Exceeded Claude continuation-round limit.",
        )



# Main experiment

def confirm_collection(total_runs):
    print("Mode:", RUN_MODE)
    print("Collection:", COLLECTION_NAME)
    print("Independent requests:", total_runs)
    print("Output directory:", COLLECTION_DIR)
    print()

    expected = "RUN PILOT" if RUN_MODE == "pilot" else "RUN COLLECTION"
    confirmation = input("Type {} to continue: ".format(expected)).strip()

    if confirmation != expected:
        raise SystemExit("Collection cancelled.")


def main():
    if COLLECTION_DIR.exists():
        raise FileExistsError(
            "Collection directory already exists: {}".format(COLLECTION_DIR)
        )

    openai_key, anthropic_key = load_api_keys()
    openai_runs = create_runs("openai")
    claude_runs = create_runs("claude")
    all_runs = openai_runs + claude_runs

    confirm_collection(len(all_runs))
    COLLECTION_DIR.mkdir(parents=True)
    create_run_folders(all_runs)

    save_json(
        COLLECTION_DIR / "collection.json",
        {
            "collection_name": COLLECTION_NAME,
            "run_mode": RUN_MODE,
            "collection_type": "batch_pilot" if RUN_MODE == "pilot" else "official",
            "purpose": COLLECTION_PURPOSE,
            "created_at_utc": utc_now(),
            "repetitions_per_condition_per_provider": REPETITIONS,
            "planned_runs": len(all_runs),
            "chronological_order_controlled": False,
            "runs": all_runs,
        },
    )

    openai_client = OpenAI(api_key=openai_key, max_retries=0, timeout=REQUEST_TIMEOUT_SECONDS)
    claude_client = Anthropic(api_key=anthropic_key, max_retries=0, timeout=REQUEST_TIMEOUT_SECONDS)

    print("\nSubmitting OpenAI batch...")
    openai_batch_id = submit_openai_batch(openai_client, openai_runs)

    print("Submitting Claude batch...")
    collect_claude(claude_client, claude_runs)

    print("\nWaiting for OpenAI batch...")
    openai_batch = wait_for_openai_batch(openai_client, openai_batch_id)
    save_openai_results(openai_client, openai_batch)

    completed = 0
    failed = []

    for run in all_runs:
        metadata = load_json(
            COLLECTION_DIR / "runs" / run["run_id"] / "metadata.json"
        )
        if metadata["status"] == "completed":
            completed += 1
        else:
            failed.append(run["run_id"])

    print("\nCollection finished.")
    print("Completed valid runs:", completed)
    print("Technical failures:", len(failed))

    if failed:
        print("Review these runs before creating replacements:")
        for run_id in failed:
            print(" -", run_id)


if __name__ == "__main__":
    main()