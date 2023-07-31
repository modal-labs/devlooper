import enum
import logging
from dataclasses import dataclass
from typing import List

import openai
from openai_function_call import OpenAISchema
from pydantic import Field
from smol_dev.prompts import SMOL_DEV_SYSTEM_PROMPT
from tenacity import (
    after_log,
    retry,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)

retry_dec = retry(
    wait=wait_random_exponential(min=5, max=120),
    stop=stop_after_attempt(8),
    after=after_log(logger, logging.WARN),
)


@retry_dec
def debug_code(
    prompt: str,
    current_file_content: str,
    current_file_path: str,
    file_paths: List[str],
    diagnosis: str,
    model: str,
) -> str:
    # Not using OpenAI schema here because of JSON decoding issues.

    completion = openai.ChatCompletion.create(
        model=model,
        temperature=0.7,
        messages=[
            {
                "role": "system",
                "content": f"""{SMOL_DEV_SYSTEM_PROMPT}

    You will be given a user's prompt for a program they want, the output of tests that were run on the program, and a possible diagnosis of the issue.

    Given this information, and one of the files, determine if the file is the source of the bug, and if so, fix it.

    If the file is the source of the bug, output the fixed code. Otherwise, output the string `None` and NOTHING ELSE.

    Only write valid code for the given filepath and file type, and return only the code. *DO NOT* include comments explaining what the bug was, or add any other explanation.""",
            },
            {
                "role": "user",
                "content": f""" I want a: {prompt} """,
            },
            {
                "role": "user",
                "content": f""" The full list of file paths is {file_paths}. The path of the current file is {current_file_path}. Its contents are: {current_file_content} """,
            },
            {
                "role": "user",
                "content": f""" A likely diagnosis for the bug is: {diagnosis} """,
            },
            {
                "role": "user",
                "content": """ - MOST IMPORTANT OF ALL every line of code you generate must be valid code. Do not include code fences in your response, for example

    Bad response (because it contains the code fence):
    ```javascript
    console.log("hello world")
    ```

    Good response (because it only contains the code):
    console.log("hello world")

    Begin generating the code now. """,
            },
        ],
    )
    text = completion.choices[0].message.content
    if text.endswith("None"):
        return current_file_content
    return text


class PackagesNeeded(OpenAISchema):
    """A list of packages needed."""

    packages: List[str]


@retry_dec
def initial_packages_needed(prompt: str, plan: str, package_manager: str, model: str):
    completion = openai.ChatCompletion.create(
        model=model,
        temperature=0.7,
        functions=[PackagesNeeded.openai_schema],
        function_call={"name": "PackagesNeeded"},
        messages=[
            {
                "role": "system",
                "content": f"""{SMOL_DEV_SYSTEM_PROMPT}

    When given their intent, create a list of packages installable via {package_manager} that the user would want to install for the program.

    Do not include packages part of the standard library already.

    Do not add any other explanation, only return a list of strings.
                  """,
            },
            {
                "role": "user",
                "content": f""" I want a: {prompt} """,
            },
            {
                "role": "user",
                "content": f""" The plan we have agreed on is: {plan} """,
            },
        ],
    )
    return PackagesNeeded.from_response(completion).packages


@retry_dec
def diagnose_issue(
    prompt: str,
    plan: str,
    file_paths: List[str],
    test_command: str,
    test_stdout: str,
    test_stderr: str,
    model: str,
) -> str:
    completion = openai.ChatCompletion.create(
        model=model,
        temperature=0.7,
        messages=[
            {
                "role": "system",
                "content": f"""{SMOL_DEV_SYSTEM_PROMPT}

        You will be given a user's prompt for a program they want, and the output of tests that were run on the program.
    `
        Given this information, and a list of the file paths, come up with a short diagnosis of what the issue is. Along with each suggested change, include the file path that the change should be made in.

        You may also suggest packages that should be installed or changes to the environment that should be made.

        Do not provide any general advice that does not fix these issues. """,
            },
            {
                "role": "user",
                "content": f""" I want a: {prompt} """,
            },
            {
                "role": "user",
                "content": f""" The plan we have agreed on is: {plan} """,
            },
            {
                "role": "user",
                "content": f""" The full list of file paths is {file_paths}.""",
            },
            {
                "role": "user",
                "content": f""" After running {test_command}, the stdout was: {test_stdout} """,
            },
            {
                "role": "user",
                "content": f""" After running {test_command}, the stderr was: {test_stderr} """,
            },
        ],
    )

    return completion.choices[0].message.content


@dataclass
class DebugPlan:
    debug_file_paths: List[str]
    install_packages: List[str]
    run_commands: List[str]


@retry_dec
def plan_debug_actions(
    prompt: str,
    package_manager: str,
    file_paths: List[str],
    diagnosis: str,
    model: str,
) -> DebugPlan:
    FilePath = enum.Enum("FilePaths", {path: path for path in file_paths})

    # Create another class so it has the right enum values.
    class _DebugPlan(OpenAISchema):
        """A plan to fix the given bugs in the program."""

        debug_file_paths: List[FilePath] = Field(..., description="The file paths to debug.")
        install_packages: List[str] = Field(..., description="The packages to install.")
        run_commands: List[str] = Field(..., description="Bash commands to run during image build.")

    completion = openai.ChatCompletion.create(
        model=model,
        temperature=0.7,
        functions=[_DebugPlan.openai_schema],
        function_call={"name": "_DebugPlan"},
        messages=[
            {
                "role": "system",
                "content": f"""{SMOL_DEV_SYSTEM_PROMPT}

    You will be given a user's prompt for a program they want, the output of tests that were run on the program, and a diagnosis for the issue.

    Given this information, and a list of the file paths, output:

    1. Any files that need to be corrected

    2. Any packages that needs to be installed in the environment via {package_manager}. Do not reinstall packages that are already installed.

    3. Any commands that need to be run (e.g. `apt-get install -y pkg-config`). Note that the OS is Debian-based. Do not use sudo in the command.

    *DO NOT* add any other explanation.""",
            },
            {
                "role": "user",
                "content": f""" I want a: {prompt} """,
            },
            {
                "role": "user",
                "content": f""" The full list of file paths is {file_paths}.""",
            },
            {
                "role": "user",
                "content": f""" A likely diagnosis for the bug is: {diagnosis} """,
            },
        ],
    )

    _plan = _DebugPlan.from_response(completion)
    return DebugPlan(
        debug_file_paths=[fp.value for fp in _plan.debug_file_paths],
        install_packages=_plan.install_packages,
        run_commands=_plan.run_commands,
    )
