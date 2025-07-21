from urllib.parse import urljoin
from datetime import datetime, timedelta
import base64
import uuid
import json
import os

import aiofiles
import aiohttp
import uvicorn
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from typing import Annotated
from jinja2 import Environment, FileSystemLoader

from tasks import delete_expired_data

WINDMILL_URL = "http://localhost/"
VALIDATION_DATA_DIR = "validation_data/"
os.makedirs(VALIDATION_DATA_DIR, exist_ok=True)

templates = Environment(loader=FileSystemLoader("templates/"))

app = FastAPI()


@app.get("/")
async def index_page():
    template = templates.get_template("index.html")
    return HTMLResponse(template.render())


@app.get("/validation/cnh/")
async def validation_page():
    template = templates.get_template("validation.html")
    return HTMLResponse(template.render())


@app.post("/validation/cnh/")
async def validation_api(
    request: Request,
    cnh_front: Annotated[UploadFile, File()],
    cnh_qrcode: Annotated[UploadFile, File()],
):
    # get host url
    port_str = f":{request.url.port}" if request.url.port else ""
    # the '//' after scheme was removed due to some issue with the way mostQI parses the redirect url for liveness test
    host_url = f"{request.url.scheme}:{request.url.hostname}{port_str}"

    # get an uuid for the current validation session and create a session url
    validation_id = str(uuid.uuid4())
    # validation_url = urljoin(host_url, f"/validation/cnh/{validation_id}")
    validation_url = host_url + f"/validation/cnh/{validation_id}"

    # convert input files into base64 strings
    cnh_front_b64 = base64.encodebytes(await cnh_front.read()).decode().strip()
    cnh_qrcode_b64 = base64.encodebytes(await cnh_qrcode.read()).decode().strip()

    # post to the windmill validation flow api
    cnh_validation_step_1_url = urljoin(WINDMILL_URL, "/api/r/cnh_validation_step_1")
    data = {
        "cnh_front": cnh_front_b64,
        "cnh_qrcode": cnh_qrcode_b64,
        "redirect_url": validation_url,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(cnh_validation_step_1_url, json=data) as res:
            res_json = await res.json()

    # TODO: handle api errors
    if "error" in res_json.keys():
        print(res_json["error"])
        print(res_json["message"])
        return Response(status_code=502)

    # save session data for posterior validation
    validation_data = {
        "user_data": res_json["user_data"],
        "liveness_pid": res_json["liveness_pid"],
        "expires": str(datetime.now() + timedelta(minutes=55)),
    }
    validation_data_path = f"{os.path.join(VALIDATION_DATA_DIR, validation_id)}.json"
    async with aiofiles.open(validation_data_path, "w", encoding="utf8") as f:
        await f.write(json.dumps(validation_data, indent=2))

    return JSONResponse({"liveness_url": res_json["liveness_url"]})


@app.get("/validation/cnh/{id}")
async def validation_confirmation(id: str):
    # delete expired session data files before proceeding
    delete_expired_data()

    # return a 404 error if the session data does not exist
    validation_data_path = f"{os.path.join(VALIDATION_DATA_DIR, id)}.json"
    if not os.path.exists(validation_data_path):
        return JSONResponse({"message": "Session not found"}, 404)

    # read session data
    async with aiofiles.open(validation_data_path, "r", encoding="utf8") as f:
        session_data = json.loads(await f.read())

    # delete session data file
    os.remove(validation_data_path)

    # post to the second step of windmill validation flow api
    cnh_validation_step_2_url = urljoin(WINDMILL_URL, "/api/r/cnh_validation_step_2")
    data = {
        "user_data": session_data["user_data"],
        "liveness_pid": session_data["liveness_pid"],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(cnh_validation_step_2_url, json=data) as res:
            res_json = await res.json()

    # TODO: handle api errors
    if "error" in res_json.keys():
        print(res_json["error"])
        print(res_json["message"])
        return Response(status_code=502)

    template = templates.get_template("success.html")
    return HTMLResponse(template.render({"name": session_data["user_data"]["nome"]}))


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=6231,
    )
