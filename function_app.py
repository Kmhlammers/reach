import json
import logging

import azure.functions as func

from reach_processor import process_reach_workbook

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="process_reach_file", methods=["POST"])
def process_reach_file(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("process_reach_file called")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    required_fields = [
        "file_id",
        "file_name",
        "site_url",
        "file_path",
        "file_link",
        "source_type",
    ]

    missing = [field for field in required_fields if not body.get(field)]
    if missing:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Missing required fields", "missing": missing}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        result = process_reach_workbook(body)
        return func.HttpResponse(
            json.dumps(result, default=str),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as exc:
        logging.exception("Failed to process workbook")
        return func.HttpResponse(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "file_id": body.get("file_id"),
                    "file_name": body.get("file_name"),
                }
            ),
            status_code=500,
            mimetype="application/json",
        )
