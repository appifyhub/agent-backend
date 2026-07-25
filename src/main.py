import dataclasses
import multiprocessing
import os
import random
import subprocess
import sys
import tomllib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import SecretStr
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse

from api.attachments_controller import AttachmentsController
from api.auth import (
    get_chat_type_from_jwt,
    get_user_id_from_jwt,
    verify_api_key,
    verify_gumroad_auth_key,
    verify_jwt_credentials,
    verify_public_attachment_token,
    verify_telegram_auth_key,
    verify_whatsapp_signature,
    verify_whatsapp_webhook_challenge,
)
from api.model.bind_license_key_payload import BindLicenseKeyPayload
from api.model.chat_settings_payload import ChatSettingsPayload
from api.model.chat_settings_response import ChatSettingsResponse
from api.model.connect_key_response import ConnectKeyResponse
from api.model.credit_transfer_payload import CreditTransferPayload
from api.model.external_tools_response import ExternalToolsResponse
from api.model.gumroad_ping_payload import GumroadPingPayload
from api.model.products_response import ProductsResponse
from api.model.release_output_payload import ReleaseOutputPayload
from api.model.settings_link_response import SettingsLinkResponse
from api.model.sponsorship_payload import SponsorshipPayload
from api.model.user_settings_payload import UserSettingsPayload
from api.model.user_settings_response import UserSettingsResponse
from db.model.chat_config import ChatConfigDB
from db.sql import get_session, initialize_db
from di.di import DI
from features.accounting.purchases.purchase_aggregates import PurchaseAggregates
from features.accounting.purchases.purchase_record import PurchaseRecord
from features.accounting.usage.usage_aggregates import UsageAggregates
from features.accounting.usage.usage_record import UsageRecord
from features.chat.telegram.model.update import Update as TelegramUpdate
from features.chat.telegram.release_summary_responder import respond_with_summary
from features.chat.telegram.telegram_update_responder import respond_to_update
from features.chat.whatsapp.model.update import Update as WhatsAppUpdate
from features.chat.whatsapp.whatsapp_update_responder import respond_to_update as respond_to_whatsapp_update
from features.currencies.asset_alert_responder import respond_with_asset_alerts
from features.integrations.integrations import resolve_agent_user
from util import log
from util.config import Config, config
from util.error_codes import INVALID_CHAT_TYPE_TOKEN, UNEXPECTED_ERROR
from util.errors import ServiceError, ValidationError
from util.functions import parse_gumroad_form


# noinspection PyUnusedLocal
@asynccontextmanager
async def lifespan(owner: FastAPI):
    process_name = multiprocessing.current_process().name
    worker_type = "main" if process_name == "MainProcess" else "worker"
    worker_info = f"[{worker_type}-{os.getpid()}] {process_name}"
    log.i(f"Lifecycle: Starting up {worker_info}")
    initialize_db()
    yield  # this holds the app alive until the server is shut down
    log.i(f"Lifecycle: Shutting down {worker_info}...")


app = FastAPI(
    docs_url = None,
    redoc_url = None,
    title = "The Agent's API",
    description = "This is the API service for The Agent.",
    debug = config.log_level in ["local", "trace", "debug"],
    lifespan = lifespan,
)

# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_credentials = False,
    allow_methods = ["*"],
    allow_headers = ["*"],
)


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    log.e(exc)
    return JSONResponse(status_code = exc.http_status, content = exc.to_api_dict())


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.e("Unexpected error", exc)
    return JSONResponse(
        status_code = 500,
        content = {"error_code": UNEXPECTED_ERROR, "message": "An unexpected error occurred", "emoji": "⚠️"},
    )


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url = config.website_url)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": config.version}


@app.post("/telegram/chat-update")
async def telegram_chat_update(
    update: TelegramUpdate,
    offloader: BackgroundTasks,
    _ = Depends(verify_telegram_auth_key),
) -> dict:
    offloader.add_task(respond_to_update, update)
    return {"status": "ok"}


@app.get("/whatsapp/chat-update")
async def whatsapp_webhook_verification(
    hub_mode: str = Query(alias = "hub.mode"),
    hub_challenge: str = Query(alias = "hub.challenge"),
    hub_verify_token: str = Query(alias = "hub.verify_token"),
) -> PlainTextResponse:
    challenge = verify_whatsapp_webhook_challenge(hub_mode, hub_challenge, hub_verify_token)
    return PlainTextResponse(content = challenge)


@app.post("/whatsapp/chat-update")
async def whatsapp_chat_update(
    request: Request,
    offloader: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default = None),
) -> dict:
    body = await request.body()
    verify_whatsapp_signature(body, x_hub_signature_256)
    update_dict = await request.json()
    update = WhatsAppUpdate.model_validate(update_dict)
    log.d(f"Received WhatsApp update: {update}")
    offloader.add_task(respond_to_whatsapp_update, update)
    return {"status": "ok"}


@app.post("/webhooks/gumroad/ping/{auth_token}")
async def gumroad_ping(
    auth_token: str,
    request: Request,
    db = Depends(get_session),
) -> dict:
    verify_gumroad_auth_key(auth_token)
    form_data = await request.form()
    form_dict = parse_gumroad_form(dict(form_data))  # type: ignore
    payload = GumroadPingPayload.model_validate(form_dict)
    DI(db).gumroad_controller.handle_ping(payload)
    return {"status": "OK"}


@app.post("/notify/price-alerts")
def notify_of_asset_alerts(
    db = Depends(get_session),
    _ = Depends(verify_api_key),
) -> dict:
    agent_user = resolve_agent_user(ChatConfigDB.ChatType.background)
    assert agent_user.id is not None
    di = DI(db, agent_user.id.hex)
    return respond_with_asset_alerts(di)


@app.post("/notify/release")
def notify_of_release(
    payload: ReleaseOutputPayload,
    db = Depends(get_session),
    _ = Depends(verify_api_key),
) -> dict:
    agent_user = resolve_agent_user(ChatConfigDB.ChatType.background)
    assert agent_user.id is not None
    di = DI(db, agent_user.id.hex)
    return respond_with_summary(payload, di)


@app.post("/task/cleanup")
def cleanup(
    db = Depends(get_session),
    _ = Depends(verify_api_key),
) -> dict:
    result = DI(db).cleanup_service.run()
    result_map = dataclasses.asdict(result)
    log.i("Responding to cleanup request", result_map)
    return result_map


@app.get("/attachments/private/{attachment_id}")
def get_private_attachment(
    attachment_id: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> StreamingResponse:
    invoker_id_hex = get_user_id_from_jwt(token)
    return AttachmentsController(DI(db, invoker_id_hex)).stream_private_attachment(attachment_id)


@app.get("/attachments/public/{token}")
def get_public_attachment(
    token: str,
    db = Depends(get_session),
) -> StreamingResponse:
    token_claims = verify_public_attachment_token(token)  # it's not header auth, so we can't use Depends here
    invoker_id_hex = token_claims.issuer_user_id
    return AttachmentsController(DI(db, invoker_id_hex)).stream_public_attachment(token_claims)


@app.get("/settings/user/{user_id}")
def get_user_settings(
    user_id: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> UserSettingsResponse:
    log.d(f"Fetching user settings for '{user_id}'")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.settings_controller.fetch_user_settings(user_id)


@app.patch("/settings/user/{user_id_hex}")
def save_user_settings(
    user_id_hex: str,
    payload: UserSettingsPayload,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> dict:
    log.d(f"Saving user settings for user '{user_id_hex}'")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    di.settings_controller.save_user_settings(user_id_hex, payload)
    return {"status": "OK"}


@app.get("/settings/chats")
def get_chats(
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> list[ChatSettingsResponse]:
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.settings_controller.fetch_all_chat_settings()


@app.get("/settings/chats/{chat_id}")
def get_chat_settings(
    chat_id: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> ChatSettingsResponse:
    log.d(f"Fetching chat settings for chat '{chat_id}'")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.settings_controller.fetch_chat_settings(chat_id)


@app.patch("/settings/chats/{chat_id}")
def save_chat_settings(
    chat_id: str,
    payload: ChatSettingsPayload,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> dict:
    log.d(f"Saving chat settings for chat '{chat_id}'")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    di.settings_controller.save_chat_settings(chat_id, payload)
    return {"status": "OK"}


@app.get("/settings/user/{user_id}/tools")
def get_tools(
    user_id: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> ExternalToolsResponse:
    log.d(f"Fetching tools for {user_id}")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.settings_controller.fetch_external_tools(user_id)


@app.get("/settings/user/{user_id}/products")
def get_products(
    user_id: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> ProductsResponse:
    log.d(f"Fetching products for {user_id}")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.settings_controller.fetch_products(user_id)


@app.get("/user/{user_id}/sponsorships")
def get_sponsorships(
    user_id: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> dict:
    log.d(f"Fetching sponsorships for {user_id}")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.sponsorships_controller.fetch_sponsorships(user_id)


@app.post("/user/{user_id}/sponsorships")
def sponsor_user(
    user_id: str,
    payload: SponsorshipPayload,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> dict:
    log.d(f"Sponsoring user from {user_id}")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.sponsorships_controller.sponsor_user(user_id, payload)


@app.delete("/user/{user_id}/sponsorships/{platform}/{platform_handle}")
def unsponsor_user(
    user_id: str,
    platform: str,
    platform_handle: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> dict:
    log.d(f"Unsponsoring user from {user_id}")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    di.sponsorships_controller.unsponsor_user(user_id, platform, platform_handle)
    return {"status": "OK"}


@app.delete("/user/{user_id}/sponsored")
def unsponsor_self(
    user_id: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> dict:
    log.d(f"User {user_id} is unsponsoring themselves")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    di.sponsorships_controller.unsponsor_self(user_id)
    return {"status": "OK"}


@app.post("/user/{user_id}/transfers")
def transfer_credits(
    user_id: str,
    payload: CreditTransferPayload,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> dict:
    log.d(f"Transferring credits from {user_id}")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    di.transfers_controller.transfer_credits(user_id, payload)
    return {"status": "OK"}


@app.get("/user/{user_id}/usage")
def get_usage_records(
    user_id: str,
    skip: int = 0,
    limit: int = 50,
    start_date: str | None = None,
    end_date: str | None = None,
    exclude_self: bool = False,
    include_sponsored: bool = False,
    include_transfers: bool = True,
    only_transfers: bool = False,
    tool_id: str | None = None,
    purpose: str | None = None,
    provider_id: str | None = None,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> list[UsageRecord]:
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    start_date_obj = datetime.fromisoformat(start_date) if start_date else None
    end_date_obj = datetime.fromisoformat(end_date) if end_date else None
    di = DI(db, invoker_id_hex)
    return di.usage_controller.fetch_usage_records(
        user_id_hex = user_id,
        skip = skip,
        limit = limit,
        start_date = start_date_obj,
        end_date = end_date_obj,
        exclude_self = exclude_self,
        include_sponsored = include_sponsored,
        include_transfers = include_transfers,
        only_transfers = only_transfers,
        tool_id = tool_id,
        purpose = purpose,
        provider_id = provider_id,
    )


@app.get("/user/{user_id}/usage/stats")
def get_usage_stats(
    user_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    exclude_self: bool = False,
    include_sponsored: bool = False,
    include_transfers: bool = True,
    only_transfers: bool = False,
    tool_id: str | None = None,
    purpose: str | None = None,
    provider_id: str | None = None,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> UsageAggregates:
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    start_date_obj = datetime.fromisoformat(start_date) if start_date else None
    end_date_obj = datetime.fromisoformat(end_date) if end_date else None
    di = DI(db, invoker_id_hex)
    return di.usage_controller.fetch_usage_aggregates(
        user_id_hex = user_id,
        start_date = start_date_obj,
        end_date = end_date_obj,
        exclude_self = exclude_self,
        include_sponsored = include_sponsored,
        include_transfers = include_transfers,
        only_transfers = only_transfers,
        tool_id = tool_id,
        purpose = purpose,
        provider_id = provider_id,
    )


@app.get("/user/{user_id}/purchases")
def get_purchase_records(
    user_id: str,
    skip: int = 0,
    limit: int = 50,
    start_date: str | None = None,
    end_date: str | None = None,
    product_id: str | None = None,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> list[PurchaseRecord]:
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    start_date_obj = datetime.fromisoformat(start_date) if start_date else None
    end_date_obj = datetime.fromisoformat(end_date) if end_date else None
    di = DI(db, invoker_id_hex)
    return di.purchases_controller.fetch_purchase_records(
        user_id_hex = user_id,
        skip = skip,
        limit = limit,
        start_date = start_date_obj,
        end_date = end_date_obj,
        product_id = product_id,
    )


@app.get("/user/{user_id}/purchases/stats")
def get_purchase_stats(
    user_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    product_id: str | None = None,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> PurchaseAggregates:
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    start_date_obj = datetime.fromisoformat(start_date) if start_date else None
    end_date_obj = datetime.fromisoformat(end_date) if end_date else None
    di = DI(db, invoker_id_hex)
    return di.purchases_controller.fetch_purchase_aggregates(
        user_id_hex = user_id,
        start_date = start_date_obj,
        end_date = end_date_obj,
        product_id = product_id,
    )


@app.post("/user/{user_id}/purchases")
def bind_purchase_license_key(
    user_id: str,
    payload: BindLicenseKeyPayload,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> PurchaseRecord:
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.purchases_controller.bind_license_key(
        user_id_hex = user_id,
        license_key = payload.license_key,
    )


@app.get("/user/{user_id_hex}/connect-key")
def get_connect_key(
    user_id_hex: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> ConnectKeyResponse:
    log.d(f"Fetching connect key for user '{user_id_hex}'")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.profile_connect_controller.get_connect_key(user_id_hex)


@app.post("/user/{user_id_hex}/regenerate-connect-key")
def regenerate_connect_key(
    user_id_hex: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> ConnectKeyResponse:
    log.d(f"Regenerating connect key for user '{user_id_hex}'")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    return di.profile_connect_controller.regenerate_connect_key(user_id_hex)


@app.post("/user/{user_id_hex}/connect-key/{connect_key}/merge")
def connect_profiles(
    user_id_hex: str,
    connect_key: str,
    db = Depends(get_session),
    token: dict[str, Any] = Depends(verify_jwt_credentials),
) -> SettingsLinkResponse:
    log.d(f"Executing profile connect for user '{user_id_hex}' with key '{connect_key}'")
    invoker_id_hex = get_user_id_from_jwt(token)
    log.d(f"  Invoker ID: {invoker_id_hex}")
    di = DI(db, invoker_id_hex)
    chat_type_str = get_chat_type_from_jwt(token)
    chat_type = ChatConfigDB.ChatType.lookup(chat_type_str)
    if not chat_type:
        raise ValidationError(f"Invalid chat type in the access token: {chat_type_str}", INVALID_CHAT_TYPE_TOKEN)
    return di.profile_connect_controller.connect_profiles(user_id_hex, connect_key, chat_type)


# The main runner
if __name__ == "__main__":
    if "--dev" in sys.argv:  # when running locally...
        os.environ["LOG_LEVEL"] = "debug"
        config.log_level = "debug"
        os.environ["API_KEY"] = "developer"
        config.api_key = SecretStr("developer")
        workers = 1
        reload = True
        print("INFO:     Launching in dev mode...")
    else:  # when running in production...
        # generate a random API key to prevent use of the default API key
        if config.api_key.get_secret_value() == Config.DEV_API_KEY:
            api_key = str(UUID(int = random.randint(0, 2 ** 128 - 1))).upper()
            os.environ["API_KEY"] = api_key
            config.api_key = SecretStr(api_key)
            print("WARN:     Generated a new API key!", config.api_key.get_secret_value(), file = sys.stderr)
        workers = 1
        reload = False
        # and run the database migrations
        print("INFO:     Running database migrations...")
        subprocess.run(["./tools/db_apply_migration", "-y"], check = True)
        print("INFO:     Launching in production mode...")
    uvicorn_log_level = "debug" if config.log_level == "local" else config.log_level

    # get the service version
    if (pyproject_file := Path("./pyproject.toml")).exists():
        with open(pyproject_file, "rb") as f:
            data = tomllib.load(f)
            version_name = data.get("project", {}).get("version", "").strip()
        if version_name:
            os.environ["VERSION"] = version_name
            config.version = version_name
            print("INFO:     Version loaded from pyproject.toml", f"v{config.version}")
        else:
            print("WARN:     Version field empty in pyproject.toml, using dev version", file = sys.stderr)
    else:
        print("WARN:     pyproject.toml not found, using dev version", file = sys.stderr)

    # finally, start the server
    uvicorn.run(
        "main:app",
        host = "0.0.0.0",
        port = 80,
        log_level = uvicorn_log_level,
        workers = workers,
        reload = reload,
    )
