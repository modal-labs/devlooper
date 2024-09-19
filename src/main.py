import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Tuple

import modal

from .env_templates import TEMPLATES, EnvTemplate

MAX_CONCURRENT_GENERATIONS = 3


@dataclass
class State:
    input_prompt: str
    code: Dict[str, str]
    package_layers: List[List[str]]
    run_commands: List[List[str]]

    def prompt(self) -> str:
        packages: List[str] = sum(self.package_layers, [])
        return f"{self.input_prompt}\n\nAssume you have these packages installed: {packages}"


app = modal.App("devlooper")

devlooper_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install("git+https://github.com/smol-ai/developer.git")
    .pip_install("colorama")
)


def write_files(code: Dict[str, str], dir: Path):
    for file_path, contents in code.items():
        p = dir / file_path
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            f.write(contents)


def run_in_sandbox(state: State, template: EnvTemplate) -> Tuple[int, str, str]:
    local_dir = Path(TemporaryDirectory().name)
    write_files(state.code, local_dir)

    image = template.image

    # TODO: install packages and run commands in the right order (maybe just build an image object incrementally
    # in the state?)
    for commands in state.run_commands:
        image = image.run_commands(*commands)

    # Install package lists in stages (so that previously installed layers don't get rebuilt)
    for package_list in state.package_layers:
        image = template.install_packages(image, package_list)

    sb = modal.Sandbox.create(
        "bash",
        "-c",
        template.test_cmd,
        image=image,
        mounts=[
            modal.Mount.from_local_dir(
                local_dir,
                remote_path=template.workdir,
            )
        ],
        timeout=120,
        workdir=template.workdir,
    )

    sb.wait()

    return (sb.returncode, sb.stdout.read(), sb.stderr.read())


@app.function(
    image=devlooper_image,
    secrets=[modal.Secret.from_name("openai-secret")],
    timeout=30 * 60,  # 30 minutes
)
async def devlooper(input_prompt: str, template_name: str, model: str = "gpt-4-1106-preview") -> State:
    from smol_dev.prompts import generate_code, plan, specify_file_paths

    from .display import print_diff, print_info, print_section_header
    from .prompts import (
        debug_code,
        diagnose_issue,
        initial_packages_needed,
        plan_debug_actions,
    )

    try:
        template = TEMPLATES[template_name]
    except KeyError:
        raise ValueError(f"Unknown template name {template_name}. Must be one of {TEMPLATES.keys()}")

    input_prompt = f"{input_prompt}\n{template.prompt}"

    print_section_header("Generating initial plan...")
    current_plan = plan(input_prompt, model=model)
    print(current_plan)

    print_section_header("Generating initial packages...")
    initial_packages = initial_packages_needed(input_prompt, current_plan, template.package_manager, model=model)
    print(initial_packages)

    state = State(input_prompt=input_prompt, code={}, package_layers=[initial_packages], run_commands=[])

    print_section_header("Generating file paths...")
    file_paths = specify_file_paths(state.prompt(), current_plan, model=model)
    print(file_paths)

    # OpenAI rate limits make this necessary.
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)

    async def gen(file_path):
        async with semaphore:
            return file_path, await generate_code(state.prompt(), current_plan, file_path, model=model)

    coros = [gen(file_path) for file_path in file_paths]
    state.code = dict(await asyncio.gather(*coros))

    i = 0
    yield i, state
    returncode, stdout, stderr = run_in_sandbox(state, template)

    while returncode != 0:
        i += 1
        print_section_header(f"Iteration {i}")

        diagnosis = diagnose_issue(
            state.prompt(),
            current_plan,
            file_paths,
            template.test_cmd,
            stdout,
            stderr,
            model=model,
        )
        print(diagnosis)

        actions = plan_debug_actions(
            state.prompt(),
            template.package_manager,
            file_paths,
            diagnosis,
            model=model,
        )

        if actions.install_packages:
            print_info(f"Installing packages {actions.install_packages}.")
            state.package_layers.append(actions.install_packages)

        if actions.run_commands:
            print_info(f"Running commands {actions.run_commands}.")
            state.run_commands.append(actions.run_commands)

        for file_path in actions.debug_file_paths:
            print_info(f"Debugging {file_path}...")

            original_code = state.code[file_path]

            updated_code = debug_code(
                state.prompt(),
                original_code,
                file_path,
                file_paths,
                diagnosis,
                model=model,
            )

            if updated_code != original_code:
                print_diff(original_code, updated_code)
                state.code[file_path] = updated_code
            else:
                print("No changes made.")

        yield i, state
        returncode, stdout, stderr = run_in_sandbox(state, template)

    print_section_header("Success!")


@app.local_entrypoint()
def main(
    prompt: str = "Create a Tic-Tac-Toe game.",
    template: str = "react",
    output_path: str = "output",
):
    for i, state in devlooper.remote_gen(prompt, template):
        path = Path(output_path) / app.app_id / str(i)

        print("Writing files to", path.absolute())
        write_files(state.code, path)

        print(f"Packages: {state.package_layers}")
        print(f"Image commands: {state.run_commands}")
