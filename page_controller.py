from __future__ import annotations

import base64
import json
import mimetypes
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from fastapi.responses import Response

from astrbot.api import logger
from astrbot.api.star import Context
from astrbot.api.web import error_response, json_response, request, stream_response

from .api_aggregator import APICoreApp
from .api_aggregator.model import ItemsBatch, NamesBatch, TargetsBatch, UpdateItemsBatch

PLUGIN_NAME = "astrbot_plugin_apis"


class APIPageController:
    def __init__(
        self,
        context: Context,
        core: APICoreApp,
    ) -> None:
        self.context = context
        self.core = core
        self.cfg = core.cfg
        self.db = core.db
        self.remote = core.remote
        self.local = core.local
        self.api_mgr = core.api_mgr
        self.site_mgr = core.site_mgr
        self.site_sync_service = core.site_sync_service
        self.api_delete_service = core.api_delete_service
        self.api_test_service = core.api_test_service
        self.pool_io_service = core.pool_io_service
        self.dashboard_dir = self.cfg.dashboard_dir
        self.editor_templates_dir = self.dashboard_dir / "templates" / "editor"

    def register_routes(self) -> None:
        routes = [
            ("/page/pool", self.get_pool, ["GET"], "Get API pool"),
            ("/page/pool/files", self.get_pool_files, ["GET"], "Get pool files"),
            (
                "/page/pool/files/delete",
                self.delete_pool_files,
                ["POST"],
                "Delete pool files",
            ),
            (
                "/page/pool/export/<pool_type>",
                self.export_pool_file,
                ["GET"],
                "Export pool file",
            ),
            (
                "/page/pool/export/<pool_type>",
                self.export_pool_to_path,
                ["POST"],
                "Export pool to path",
            ),
            (
                "/page/pool/import/<pool_type>",
                self.import_pool_file,
                ["POST"],
                "Import pool file",
            ),
            (
                "/page/pool/import/<pool_type>/path",
                self.import_pool_from_default_path,
                ["POST"],
                "Import pool from default path",
            ),
            (
                "/page/editor/site-form",
                self.site_form,
                ["GET"],
                "Get site form template",
            ),
            (
                "/page/editor/api-form",
                self.api_form,
                ["GET"],
                "Get api form template",
            ),
            ("/page/site/batch", self.create_sites_batch, ["POST"], "Create sites"),
            ("/page/site/batch", self.update_sites_batch, ["PUT"], "Update sites"),
            ("/page/site/batch", self.delete_sites_batch, ["DELETE"], "Delete sites"),
            ("/page/api/batch", self.create_apis_batch, ["POST"], "Create apis"),
            ("/page/api/batch", self.update_apis_batch, ["PUT"], "Update apis"),
            ("/page/api/batch", self.delete_apis_batch, ["DELETE"], "Delete apis"),
            ("/page/test/stream", self.test_api_stream, ["GET"], "Test API stream"),
            (
                "/page/test/preview/batch",
                self.test_api_preview_batch,
                ["POST"],
                "Preview test API batch",
            ),
            ("/page/local-file", self.local_file, ["GET"], "Get local file"),
            (
                "/page/local-file/content",
                self.local_file_content,
                ["GET"],
                "Get local file content",
            ),
            ("/page/local-data", self.get_local_data, ["GET"], "Get local data"),
            (
                "/page/local-data/items/batch",
                self.get_local_data_items_batch,
                ["POST"],
                "Get local data items batch",
            ),
            (
                "/page/local-data/batch",
                self.delete_local_data_batch,
                ["POST", "DELETE"],
                "Delete local data batch",
            ),
            (
                "/page/local-data-item/batch",
                self.delete_local_data_items_batch,
                ["POST", "DELETE"],
                "Delete local data item batch",
            ),
        ]
        for route, handler, methods, desc in routes:
            self.context.register_web_api(
                f"/{PLUGIN_NAME}{route}",
                handler,
                methods,
                desc,
            )

    @staticmethod
    def _ok(data: Any = None, message: str = "", status: int = 200):
        return json_response(
            {
                "status": "ok",
                "message": message,
                "data": {} if data is None else data,
            },
            status_code=status,
        )

    @staticmethod
    def _error(message: str, status: int = 400):
        return error_response(message, status_code=status, data={})

    @staticmethod
    def _to_int(value: Any, *, default: int, minimum: int | None = None) -> int:
        try:
            parsed = int(str(value).strip())
        except Exception:
            parsed = default
        if minimum is not None and parsed < minimum:
            return default
        return parsed

    async def _read_json(self) -> dict[str, Any]:
        data = await request.json(default=None)
        if not isinstance(data, dict):
            raise ValueError("request body must be an object")
        return data

    async def _read_json_with_method(self) -> tuple[str, dict[str, Any]]:
        payload = await self._read_json()
        override_method = str(payload.pop("_method", "")).strip().upper()
        request_method = str(request.method).upper()
        method = override_method or request_method or "GET"
        return method, payload

    async def site_form(self):
        return await self._send_text_file(
            self.editor_templates_dir / "site_form.html",
            "text/html; charset=utf-8",
        )

    async def api_form(self):
        return await self._send_text_file(
            self.editor_templates_dir / "api_form.html",
            "text/html; charset=utf-8",
        )

    async def _send_text_file(self, path: Path, content_type: str):
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self._error("file not found", status=404)
        return Response(text, media_type=content_type)

    async def get_pool(self):
        self.site_sync_service.sync_all_api_sites()
        apis = [entry.to_dict() for entry in self.api_mgr.list_entries()]
        sites = self.site_mgr.attach_api_counts(
            [entry.to_dict() for entry in self.site_mgr.list_entries()],
            apis,
        )
        return self._ok(
            {
                "sites": sites,
                "apis": apis,
                "pool_io_default_dir": str(
                    self.pool_io_service.pool_files_dir.resolve()
                ),
            }
        )

    async def get_pool_files(self):
        try:
            base_dir = self.pool_io_service.pool_files_dir.resolve()
            rows = self.pool_io_service.list_pool_files()
            return self._ok(
                {
                    "files": [
                        {
                            **row,
                            "id": str(row.get("name", "")).strip(),
                            "path": str(base_dir / str(row.get("name", "")).strip()),
                        }
                        for row in rows
                    ],
                    "base_dir": str(base_dir),
                },
                "pool files listed",
            )
        except Exception as exc:
            return self._error(str(exc), status=500)

    async def delete_pool_files(self):
        try:
            payload = await self._read_json()
            raw_names = payload.get("names", [])
            if not isinstance(raw_names, list):
                return self._error("names must be a list", status=400)
            names = [str(item or "").strip() for item in raw_names]
            return self._ok(
                self.pool_io_service.delete_pool_files(names),
                "pool files deleted",
            )
        except ValueError as exc:
            return self._error(str(exc), status=400)
        except Exception as exc:
            logger.error("[api_aggregator] delete pool files failed: %s", exc)
            return self._error(f"delete failed: {exc}", status=500)

    async def export_pool_file(self, pool_type: str):
        try:
            custom_path = request.query.get("path", "")
            payload = self.pool_io_service.export_pool_as_bytes(pool_type)
            file_name = self.pool_io_service.suggest_export_file_name(
                pool_type,
                custom_path,
            )
            response = Response(
                payload,
                media_type="application/json",
            )
            response.headers["Content-Disposition"] = (
                f'attachment; filename="{file_name}"'
            )
            return response
        except ValueError as exc:
            return self._error(str(exc), status=400)
        except Exception as exc:
            logger.error("[api_aggregator] export pool failed: %s", exc)
            return self._error(f"export failed: {exc}", status=500)

    async def export_pool_to_path(self, pool_type: str):
        try:
            payload = await self._read_json()
            custom_path = str(payload.get("path", "")).strip()
            raw_items = payload.get("items")
            items = (
                [dict(item) for item in raw_items if isinstance(item, dict)]
                if isinstance(raw_items, list)
                else None
            )
            file_path = self.pool_io_service.export_pool_to_file(
                pool_type,
                custom_path,
                rows=items,
            )
            return self._ok(
                {"pool_type": pool_type, "path": str(file_path)},
                "pool exported",
            )
        except ValueError as exc:
            return self._error(str(exc), status=400)
        except Exception as exc:
            logger.error("[api_aggregator] export pool failed: %s", exc)
            return self._error(f"export failed: {exc}", status=500)

    async def import_pool_file(self, pool_type: str):
        try:
            content_type = str(request.content_type or "").lower()
            raw_bytes: bytes
            if "multipart/form-data" in content_type:
                files = await request.files()
                upload = files.get("file")
                if upload is None:
                    return self._error("missing upload file field: file", status=400)
                raw_bytes = await upload.read()
            elif "application/json" in content_type:
                payload = await self._read_json()
                content = payload.get("content")
                if not isinstance(content, str):
                    return self._error("json body requires string field: content")
                raw_bytes = content.encode("utf-8")
            else:
                raw_bytes = await request.body()
            if not raw_bytes:
                return self._error("import file is empty", status=400)
            return self._ok(
                self.pool_io_service.import_pool_from_bytes(pool_type, raw_bytes),
                "pool imported",
            )
        except ValueError as exc:
            return self._error(str(exc), status=400)
        except Exception as exc:
            logger.error("[api_aggregator] import pool failed: %s", exc)
            return self._error(f"import failed: {exc}", status=500)

    async def import_pool_from_default_path(self, pool_type: str):
        try:
            payload = await self._read_json()
            file_name = str(payload.get("name", "")).strip()
            return self._ok(
                self.pool_io_service.import_pool_from_file(pool_type, file_name),
                "pool imported",
            )
        except ValueError as exc:
            return self._error(str(exc), status=400)
        except Exception as exc:
            logger.error("[api_aggregator] import by path failed: %s", exc)
            return self._error(f"import failed: {exc}", status=500)

    async def create_sites_batch(self):
        try:
            method, payload = await self._read_json_with_method()
            if method == "PUT":
                return await self.update_sites_batch(payload)
            if method == "DELETE":
                return await self.delete_sites_batch(payload)
            if method != "POST":
                return self._error(f"unsupported method: {method}", status=405)
            items = ItemsBatch.from_raw(payload).items
            entries = self.site_mgr.add_entries(items, save=True)
            self.site_sync_service.sync_all_api_sites()
            return self._ok(
                {"items": [entry.to_dict() for entry in entries]},
                "sites created",
            )
        except Exception as exc:
            return self._error(str(exc))

    async def update_sites_batch(self, payload: dict[str, Any] | None = None):
        try:
            if payload is None:
                payload = await self._read_json()
            updates = [
                {"name": item.name, "payload": item.payload}
                for item in UpdateItemsBatch.from_raw(payload).items
            ]
            changed = self.site_mgr.update_entries(updates, save=True)
            self.site_sync_service.sync_all_api_sites()
            return self._ok({"items": changed}, "sites updated")
        except LookupError as exc:
            return self._error(str(exc), status=404)
        except Exception as exc:
            return self._error(str(exc))

    async def delete_sites_batch(self, payload: dict[str, Any] | None = None):
        try:
            if payload is None:
                method, payload = await self._read_json_with_method()
            else:
                method = "DELETE"
            if method != "DELETE":
                return self._error(f"unsupported method: {method}", status=405)
            names = NamesBatch.from_raw(payload).names
            success, failed = self.site_mgr.remove_entries(names, save=True)
            if success:
                self.site_sync_service.sync_all_api_sites()
            if not success:
                return self._error("no sites were deleted", status=404)
            return self._ok(
                {"requested": names, "deleted": success, "failed": failed},
                "sites deleted",
            )
        except Exception as exc:
            return self._error(str(exc))

    async def create_apis_batch(self):
        try:
            method, payload = await self._read_json_with_method()
            if method == "PUT":
                return await self.update_apis_batch(payload)
            if method == "DELETE":
                return await self.delete_apis_batch(payload)
            if method != "POST":
                return self._error(f"unsupported method: {method}", status=405)
            items = ItemsBatch.from_raw(payload).items
            normalized_items = [
                self.api_mgr.normalize_payload(
                    item,
                    require_unique_name=False,
                    resolve_site_name=self.site_sync_service.resolve_api_site_name,
                )
                for item in items
            ]
            entries = self.api_mgr.add_entries(
                normalized_items,
                save=True,
                emit_changed=True,
            )
            return self._ok(
                {"items": [entry.to_dict() for entry in entries]},
                "apis created",
            )
        except Exception as exc:
            return self._error(str(exc))

    async def update_apis_batch(self, payload: dict[str, Any] | None = None):
        try:
            if payload is None:
                payload = await self._read_json()
            updates = [
                {"name": item.name, "payload": item.payload}
                for item in UpdateItemsBatch.from_raw(payload).items
            ]
            changed = self.api_mgr.update_entries(
                updates,
                resolve_site_name=self.site_sync_service.resolve_api_site_name,
                save=True,
            )
            return self._ok({"items": changed}, "apis updated")
        except LookupError as exc:
            return self._error(str(exc), status=404)
        except Exception as exc:
            return self._error(str(exc))

    async def delete_apis_batch(self, payload: dict[str, Any] | None = None):
        try:
            if payload is None:
                method, payload = await self._read_json_with_method()
            else:
                method = "DELETE"
            if method != "DELETE":
                return self._error(f"unsupported method: {method}", status=405)
            names = NamesBatch.from_raw(payload).names
        except ValueError as exc:
            return self._error(str(exc))
        result = self.api_delete_service.delete_by_names(names)
        if result.ok:
            return self._ok(result.data, result.message)
        return self._error(result.message, status=result.status)

    async def test_api_stream(self):
        args = request.query
        names = args.getlist("name")
        site_names = args.getlist("site")
        csv_site_names = args.get("sites", "")
        if csv_site_names:
            site_names.extend(
                [item.strip() for item in csv_site_names.split(",") if item.strip()]
            )

        async def generate():
            try:
                async for event in self.api_test_service.stream_test_apis(
                    names=names,
                    site_names=site_names,
                    query=str(args.get("query", "")).strip(),
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.exception("[api_aggregator] test stream failed: %s", exc)
                yield f"data: {json.dumps({'event': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

        return stream_response(
            generate(),
            content_type="text/event-stream; charset=utf-8",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def test_api_preview_batch(self):
        try:
            items = ItemsBatch.from_raw(await self._read_json()).items
            details = [
                await self.api_test_service.build_preview(
                    item,
                    resolve_site_name=self.site_sync_service.resolve_api_site_name,
                )
                for item in items
            ]
            return self._ok({"items": details}, "tests finished")
        except Exception as exc:
            return self._error(str(exc))

    async def local_file(self):
        try:
            target = self.local.resolve_local_file(request.query.get("path", ""))
            payload = target.read_bytes()
            content_type, _ = mimetypes.guess_type(str(target))
            response = Response(
                payload,
                media_type=content_type or "application/octet-stream",
            )
            response.headers["Content-Disposition"] = (
                f'inline; filename="{target.name}"'
            )
            return response
        except Exception as exc:
            return self._error(str(exc), status=404 if "not found" in str(exc) else 400)

    async def local_file_content(self):
        try:
            requested_path = request.query.get("path", "")
            target = self.local.resolve_local_file(requested_path)
            payload = target.read_bytes()
            content_type, _ = mimetypes.guess_type(str(target))
            return self._ok(
                {
                    "name": target.name,
                    "path": requested_path,
                    "content_type": content_type or "application/octet-stream",
                    "content_base64": base64.b64encode(payload).decode("ascii"),
                    "size_bytes": len(payload),
                }
            )
        except Exception as exc:
            return self._error(str(exc), status=404 if "not found" in str(exc) else 400)

    async def get_local_data(self):
        try:
            args = request.query
            page = self._to_int(args.get("page", "1"), default=1, minimum=1)
            page_size_raw = args.get("page_size", "all").strip().lower()
            page_size: int | str = (
                "all"
                if page_size_raw == "all"
                else self._to_int(page_size_raw, default=20, minimum=1)
            )
            paged = self.local.list_collections_page(
                page=page,
                page_size=page_size,
                query=args.get("search", ""),
                sort_rule=args.get("sort", "name_asc"),
                type_values=self._parse_query_values(
                    args, item_key="type", csv_key="types"
                )
                or None,
            )
            return self._ok(
                {
                    "collections": paged["items"],
                    "pagination": self._pick_pagination(paged),
                }
            )
        except Exception as exc:
            return self._error(str(exc))

    async def get_local_data_items_batch(self):
        try:
            targets = TargetsBatch.from_raw(await self._read_json()).targets
            return self._ok(self.local.get_collection_items_batch(targets))
        except Exception as exc:
            return self._error(str(exc))

    async def delete_local_data_batch(self):
        try:
            method, payload = await self._read_json_with_method()
            if method != "DELETE":
                return self._error(f"unsupported method: {method}", status=405)
            targets = TargetsBatch.from_raw(payload).targets
            return self._ok(
                self.local.delete_collections_batch(targets),
                "local data deleted",
            )
        except Exception as exc:
            return self._error(str(exc))

    async def delete_local_data_items_batch(self):
        try:
            method, payload = await self._read_json_with_method()
            if method != "DELETE":
                return self._error(f"unsupported method: {method}", status=405)
            targets = TargetsBatch.from_raw(payload).targets
            return self._ok(
                self.local.delete_items_multi_batch(targets),
                "local data item deleted",
            )
        except Exception as exc:
            return self._error(str(exc))

    @staticmethod
    def _append_query_values(target: list[str], raw: Any) -> None:
        if raw is None:
            return
        if isinstance(raw, str):
            target.append(raw)
            return
        if isinstance(raw, Iterable):
            for item in raw:
                if item is not None:
                    target.append(str(item))
            return
        target.append(str(raw))

    @staticmethod
    def _parse_query_values(
        args: Any,
        *,
        item_key: str,
        csv_key: str,
    ) -> list[str]:
        values: list[str] = []
        getlist = getattr(args, "getlist", None)
        if callable(getlist):
            APIPageController._append_query_values(values, getlist(item_key))
            APIPageController._append_query_values(values, getlist(csv_key))
        else:
            single_item = args.get(item_key) if hasattr(args, "get") else None
            single_csv = args.get(csv_key) if hasattr(args, "get") else None
            APIPageController._append_query_values(values, single_item)
            APIPageController._append_query_values(values, single_csv)

        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            for part in str(value or "").split(","):
                text = part.strip()
                normalized = text.lower()
                if not text or normalized in seen:
                    continue
                seen.add(normalized)
                result.append(text)
        return result

    @staticmethod
    def _pick_pagination(paged: dict[str, Any]) -> dict[str, Any]:
        return {
            "page": int(paged.get("page", 1)),
            "page_size": paged.get("page_size", 20),
            "total": int(paged.get("total", 0)),
            "total_pages": int(paged.get("total_pages", 1)),
            "start": int(paged.get("start", 0)),
            "end": int(paged.get("end", 0)),
        }
