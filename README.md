# 🐥 devlooper

`devlooper` is a program synthesis agent that autonomously fixes its output by running tests!

Here's `devlooper` in action, taking 11 iterations to create a Python library that generates voronoi diagrams:

<p align="center">
  <img width="600" alt="devlooper demo" src="https://github.com/modal-labs/devlooper/assets/5786378/0dfa6086-96e2-484b-92c8-23d1017471ab">
</p>

## ⚙️ How it works

This project extends [smol developer](https://github.com/smol-ai/developer) by giving it access to a [sandbox](https://modal.com/docs/guide/sandbox) to run tests in. The agent iterates until all tests pass, by updating the code and fixing the environment (installing packages).

### 📦 Environment templates

The project uses environment "templates" to define the basic setup and test harness for a given language/framework. For now, three templates are provided:

- React + Jest
- Python
- Rust

However, any language/framework should work, as long as it can be installed within a container. Contributions for more templates are welcome (see [`env_templates.py`](https://github.com/modal-labs/devlooper/blob/main/src/env_templates.py)).

### 🏖️ Sandbox

We use [Modal](http://modal.com/)'s new [Sandbox](https://modal.com/docs/guide/sandbox) primitive to run tests in an isolated invornment and fetch the output. This allows us to construct the image incrementally as well (similar to building up a Dockerfile in layers that are cached).

### 🤖 Debug loop

In each iteration, the agent runs the test command for the environment. If a non-zero exit code is received, the agent passes the `stdout` and `stderr` from the sandbox to the LLM to diagnose the error. This diagnosis is used in a separate step to generate a `DebugPlan` consisting of three types of actions:

1. Inspect and fix a file
2. Install a package in the image
3. Run commands in the image

More types of actions can be implemented pretty easily — once again, contributions are welcome!

Running the diagnosis as a separate step seems to boost model accuracy by quite a bit (instead of immediately predicting the `DebugPlan`). We suspect the benefits are similar to why Chain-of-Thought prompting works so well.

## 🧑‍🚀 Usage

### Set up

- Create a [Modal](http://modal.com/) account ([reach out to us](mailto:akshat@modal.com) if you are still on the waitlist!)
- Install `modal` in your current Python environment

```bash
pip install modal
```

- Create a Modal token

```bash
modal token new
```

- Create an [OpenAI](https://openai.com/) account and get an API key
- [Create a Modal secret](https://modal.com/secrets/create) named `openai-secret`

### Generate!

You're ready to generate! From the root directory of this repo, `modal run` the program with your choice of `prompt` and `template`:

```bash
modal run src.main --prompt="a simple 2D graphics library" --template="rust"
```

```bash
modal run src.main --prompt="a todo-list app" --template="react"
```

```bash
modal run src.main --prompt="a webscraper that checks if there are new reservations for a given restaurant on Resy" --template="python"
```

Once all tests pass, the output will be written to `output/` in the same directory by default. This can be overridden using `--output-path`.

## ✨ Showcase

_Coming soon_

## 🔮 Future directions

This project is mostly a proof of concept, and there's a lot of cool additions that will make this better. Here are some ideas:

- Allowing feedback from users in the loop, or accepting an existing project + plan as input and making suggested changes to it.
- Making the debugging prompt better with relevant parts of the code, retrieved using embeddings.
- Go out and fetch the documentation for a package if needed.
- Using previous edits in the prompt somewhere to prevent the model from going into a loop.
- Synthesizing `EnvTemplate`s from scratch.
- Generalizing this to more LLMs, including open-source ones!
