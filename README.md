![License](https://img.shields.io/github/license/appifyhub/agent-backend?logo=github&logoColor=white&label=License&color=FA3080)
![Date](https://img.shields.io/github/release-date/appifyhub/agent-backend?display_date=published_at&logo=docker&logoColor=white&label=Released&color=FA3080)
![Release](https://img.shields.io/github/v/release/appifyhub/agent-backend?sort=semver&display_name=release&logo=github&logoColor=white&label=Latest&color=FA3080)  
![Code](https://img.shields.io/github/repo-size/appifyhub/agent-backend?logo=github&logoColor=white&label=Sources&color=FAFA20)
![Image](https://img.shields.io/docker/image-size/appifyhub/the-agent?sort=semver&logo=docker&logoColor=white&label=Image&color=FAFA20)  
![Build](https://img.shields.io/github/actions/workflow/status/appifyhub/agent-backend/release.yml?branch=release&logo=github&logoColor=white&label=Build)
![Issues](https://img.shields.io/github/issues-closed/appifyhub/agent-backend?logo=github&logoColor=white&label=Issues&color=blue)
![PRs](https://img.shields.io/github/issues-pr-closed/appifyhub/agent-backend?logo=github&logoColor=white&label=PRs&color=blue)

# The Agent · Our Intelligent Virtual Assistant

## About the project

This repository contains the **complete** codebase of The Agent's backend service.

The service covers for the majority of daily user-facing features, such as asking for advice, checking news, analyzing photos, generating new content, etc. Although the final product looks like a simple wrapper around the Large Language Model (LLM) technology, it's more than that – The Agent is a complex system or interconnected modules that integrate many services and APIs, and enables multiple access channels to provide a true virtual assistant experience.

See the rest of this document for a developer's overview and information on how to use it yourself.

#### Access

This service currently powers several production-level bots. For privacy reasons, we're not listing each bot here individually – but you can definitely run the service locally on your machine (for free) and connect it to your own bot. You're also welcome to use the service as a standalone backend for your own projects, assuming you have the necessary infrastructure to host it.

## Before you continue…

If you plan on contributing to this project in any way, please read and acknowledge the [Contributing guide](./CONTRIBUTING.md) first.

Please also take note of the [License](./LICENSE).

## Developer's Overview

Because the complete codebase is open-source, you can inspect and run the service yourself.

### Tech Stack

The project currently uses the following tech stack:

- Runtime: **Python**
- Language: **Python**
- Framework: **FastAPI** (with Pydantic 2)
- Persistence: **PostgreSQL** (with SQL Alchemy)
- Build System: **Pipenv** & **Custom** (see `tools` and `.github` directories)
- Continuous Integration: **GitHub Actions**
- Continuous Deployment: **Argo CD**
- Distribution: **Docker** image (managed deployment on Kubernetes)

### How to build and run?

#### Dependencies

> ℹ️  This project uses `pipenv` to manage dependencies and take care of the environment.

Using `pipenv`, you can run `pipenv install` in the root directory to set up your dependencies correctly.

Video preparation also requires the system `ffmpeg` and `ffprobe` executables. The Docker image installs
them through Debian packages. On macOS, install the native ARM or Intel build with `brew install ffmpeg`.

To prepare the production server (less logging, more parallelism):

```bash
pipenv install
```

To prepare a development system, e.g. for testing and improvement purposes:

```bash
# Install the project's development dependencies
pipenv install --dev

# Install git hooks for pre-commit checks
pipenv run pre-commit install --install-hooks
```

After the dependencies have been installed, you can run `pipenv shell` to get a new shell forked, in which the environment will be set up to easily run everything. Your Python version will be correct in there, and the dependencies will be available.

Pre-commit installation sets up a git hook to validate code quality before every commit.

> ℹ️  To exit the shell, simply run `deactivate`, followed by `exit` (if the shell hasn't closed automatically).

Exiting the shell will disconnect the dev environment from your shell session, so you will need to run `pipenv shell` again to get back into the correct environment.

Once the environment has been configured, you can run the main code.

#### Running tools

You can use the pre-built scripts located in the `tools` directory. Those are easy-to-use, single-shot Shell executables that require no developer setup.

To install dependencies and run the service in production mode:

```bash
pipenv install
pipenv run python src/main.py
```

To install dependencies and run the service in development mode:

```bash
pipenv install --dev
pipenv run python src/main.py --dev
```

To run lint checks and auto-fix them:

```bash
# Run the lint checks on *all* files
pipenv run pre-commit run --all-files --show-diff-on-failure

# Run the lint checks only on *git-staged* files
pipenv run pre-commit run
```

And most importantly, to run all tests:

```bash
pipenv run pytest -v
```

> ℹ️  Follow the command line instructions for more information during the execution of the scripts.

There are more tools in the same directory (especially useful around database migrations); feel free to explore those at your own pace when needed.

To emulate this behavior on Windows, you would need to inspect the scripts individually and mimic their behavior in the DOS environment... or open a Pull Request with a Windows-compatible version of the scripts!

#### Docker support

This final product is also available as a **Docker** image.  
For more information on how to run it using Docker, see the `Dockerfile` and the `Packages` section in the GitHub repository. There's also more information in the [Docker directory](./docker).

### License

Check out the license [here](LICENSE).

---

For frontend and user interface details, see the [web app repository](https://github.com/appifyhub/agent-backend-web-app).
