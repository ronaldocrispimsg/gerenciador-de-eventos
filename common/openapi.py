"""Registro de especificacao OpenAPI 3.0.3, Swagger UI e healthcheck."""

from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify

SWAGGER_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <title>{title} - Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <noscript>Habilite JavaScript ou acesse <a href="/openapi.json">/openapi.json</a>.</noscript>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function () {{
      if (typeof SwaggerUIBundle !== "undefined") {{
        SwaggerUIBundle({{ url: "/openapi.json", dom_id: "#swagger-ui" }});
      }} else {{
        document.getElementById("swagger-ui").innerHTML =
          "<p>Swagger UI offline. Consulte o contrato JSON em <a href='/openapi.json'>/openapi.json</a>.</p>";
      }}
    }};
  </script>
</body>
</html>
"""


def build_openapi_spec(
    title: str,
    version: str,
    description: str,
    paths: dict[str, Any],
    schemas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Constroi um documento OpenAPI 3.0.3 padronizado com suporte a Bearer JWT."""
    components: dict[str, Any] = {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Token JWT emitido pelo soa-identidade.",
            }
        }
    }
    if schemas:
        components["schemas"] = schemas

    return {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "version": version,
            "description": description,
        },
        "paths": paths,
        "components": components,
    }


def register_openapi(app: Flask, service_name: str, spec_dict: dict[str, Any]) -> None:
    """Registra rotas /openapi.json, /apispec_1.json, /apidocs, /docs e /health."""
    title = spec_dict.get("info", {}).get("title", service_name)

    @app.get("/openapi.json")
    @app.get("/apispec_1.json")
    def openapi_spec() -> Response:
        return jsonify(spec_dict)

    @app.get("/apidocs")
    @app.get("/docs")
    def swagger_ui() -> Response:
        return Response(SWAGGER_HTML.format(title=title), mimetype="text/html")

    @app.get("/health")
    def health() -> tuple[Response, int]:
        return jsonify({"status": "healthy", "service": service_name}), 200
