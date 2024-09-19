from dataclasses import dataclass
from typing import Callable, List

import modal


@dataclass
class EnvTemplate:
    # Base Modal image.
    image: modal.Image
    # Command to run to test the project.
    test_cmd: str
    # Working directory of the project. The LLM-generated code will be mounted here.
    workdir: str
    # Template-specific prompt to be appended to the user's input prompt.
    prompt: str
    # Function to extend the image and install packages in it.
    install_packages: Callable[[modal.Image, List[str]], modal.Image]
    # Package manager used by the template.
    package_manager: str


TEMPLATES = {
    "python": EnvTemplate(
        test_cmd="python -m pytest . -x",
        workdir="/app",
        image=modal.Image.debian_slim().pip_install("pytest"),
        install_packages=lambda image, packages: image.pip_install(packages),
        package_manager="pip",
        prompt="""The project must be in Python, and have tests.

                Assume you have the following file structure:
                    - setup.py
                    - test/
                    - app/

                You just have to populate app/ and test/. """,
    ),
    "rust": EnvTemplate(
        test_cmd="cargo test",
        workdir="/app",
        image=(
            modal.Image.from_registry("rust:slim")
            .apt_install("build-essential")
            .run_commands("cargo new app --bin")
            .workdir("/app")
        ),
        install_packages=lambda image, packages: image.run_commands(f"cargo add {' '.join(packages)}"),
        package_manager="cargo",
        prompt="""The project must be in Rust, and have tests.

                Assume you have the following file structure:
                    - Cargo.toml
                    - src/
                    - tests/

                You just have to populate src/ and tests/. DO NOT generate Cargo.toml.""",
    ),
    "react": EnvTemplate(
        test_cmd="yarn run jest --bail",
        workdir="/app",
        image=(
            modal.Image.from_registry("node:slim")
            .run_commands("yarn create vite app --template react")
            .workdir("/app")
            .run_commands(
                "yarn add --dev jest @testing-library/react @testing-library/jest-dom jest-environment-jsdom",
                "yarn add --dev babel-jest @babel/core @babel/preset-env @babel/preset-react",
            )
            .run_commands(
                """echo '{ "presets": [ "@babel/preset-env", ["@babel/preset-react", {runtime: "automatic"}] ] }' > babel.config.json""",
                """echo '{ "testEnvironment": "jsdom" }' > jest.config.json""",
            )
        ),
        install_packages=lambda image, packages: image.run_commands(f"yarn add {' '.join(packages)}"),
        package_manager="yarn",
        prompt="""The project must be in React, and have tests.

                Assume you have a new create-react-app project already set up with the following files:
                    - index.html
                    - package.json
                    - src/

                You just have to populate src/. Please use the .jsx extension for files with JSX.""",
    ),
}
