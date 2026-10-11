## Docker Compose support

This project can run in Docker Compose with its database and URL shortener. Attachments use persistent local storage by default, so a separate object-storage service is not required.

### Start and stop

Run these commands from the project root:

```console
docker compose --env-file docker/.env -f docker/docker-compose.yml -p agent-local up -d --wait
docker compose --env-file docker/.env -f docker/docker-compose.yml -p agent-local down
```

If Compose is installed as a standalone binary, use `docker-compose` instead of `docker compose`.

Stopping the stack preserves its named volumes. Adding `--volumes` to `down` deletes the stored data.

### How does the local Docker build work?

The basic `Dockerfile` is available in the project's root directory. It copies the necessary files into the image and installs the dependencies; tests are not executed during builds.

Compose uses the published `appifyhub/the-agent:latest` image by default.

### How do I reconfigure the project properties?

This directory contains a `.env` file with generic local examples. Edit it to configure the stack and supply credentials for the integrations you use.

Exported shell variables can override these examples. Keep signing and encryption secrets stable when reusing stored data.

Database initialization runs only for new volumes. Back up existing data before changing database versions, credentials, or storage settings.

### Word of caution

These defaults are for local testing and bind exposed services to loopback. Remote integrations need publicly reachable URLs.

**DO NOT** deploy these example settings directly to production or production-like environments.

