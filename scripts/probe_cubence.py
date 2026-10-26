#!/usr/bin/env python3
"""Real, small Responses capability probes; never writes credentials or headers."""
from __future__ import annotations
import argparse
import base64
import json
from pathlib import Path
import struct
import sys
import hashlib
import io
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy.backends.cubence import BudgetLedger, CubenceClient, ProviderError, load_config, response_text, response_tools


def color_png():
    # A red left half and blue right half is image evidence independent of text.
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind+data)&0xffffffff)
    pixels=b"".join(b"\0" + b"\xff\0\0"*32 + b"\0\0\xff"*32 for _ in range(32))
    raw=b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR", struct.pack("!2I5B",64,32,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b"")
    return "data:image/png;base64,"+base64.b64encode(raw).decode()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config",default="config/lab_cuvette_loading/Project_v1/policies/cubence_gpt6.json")
    p.add_argument("--output",required=True)
    p.add_argument("--ledger",required=True,help="Shared absolute budget ledger used by all subsequent evaluations")
    p.add_argument("--image",type=Path,help="Optional real camera RGB file for the image probe; default is the independent red/blue synthetic test")
    p.add_argument('--image-max-side',type=int,default=640,help='Declared thumbnail bound for --image; native source file remains unchanged')
    p.add_argument('--image-jpeg-quality',type=int,default=80)
    p.add_argument("--capabilities",nargs="+",choices=["text","image","tools","structured","multiturn","error"],default=["text","image","tools","structured","multiturn"])
    args=p.parse_args(argv)
    output=Path(args.output)
    if output.exists():p.error("Output already exists; preserve earlier probes")
    output.mkdir(parents=True)
    cfg=load_config(args.config)
    client=CubenceClient(cfg,BudgetLedger(args.ledger,cfg))
    evidence=dict(schema="labsim.cubence_capabilities.v1",provider=cfg["provider"],base_url=cfg["base_url"],requested_model=cfg["model"],
        endpoint="responses",responses_supported=None,probes={},secrets_persisted=False,pricing=cfg["pricing"])
    real_image=None
    if args.image:
        from PIL import Image
        if not 64<=args.image_max_side<=640 or not 30<=args.image_jpeg_quality<=95:p.error('Image bound must be64..640 and JPEG quality30..95')
        source=args.image.read_bytes();image=Image.open(io.BytesIO(source)).convert('RGB');native_size=image.size
        image.thumbnail((args.image_max_side,args.image_max_side),Image.Resampling.LANCZOS)
        encoded=io.BytesIO();image.save(encoded,format='JPEG',quality=args.image_jpeg_quality);raw=encoded.getvalue()
        real_image='data:image/jpeg;base64,'+base64.b64encode(raw).decode()
        evidence['image_source']=dict(kind='provided_real_camera_file',path=str(args.image),source_sha256=hashlib.sha256(source).hexdigest(),
            transmitted_sha256=hashlib.sha256(raw).hexdigest(),native_resolution_wh=list(native_size),transmitted_resolution_wh=list(image.size),
            format='JPEG',jpeg_quality=args.image_jpeg_quality,resize_interpolation='Pillow LANCZOS',truth_annotations_supplied=False)
    tools=[dict(type="function",name="probe_echo",description="Return the provided integer without executing anything.",strict=True,
        parameters=dict(type="object",properties={"value":{"type":"integer"}},required=["value"],additionalProperties=False))]
    last_tool_response=None
    for capability in args.capabilities:
        try:
            instruction="This is a small API capability check. Follow the user's instruction exactly."
            extra={}
            if capability=="text":items=[dict(role="user",content="Reply exactly LABSIM_PROBE_OK.")]
            elif capability=="image":items=[dict(role="user",content=[dict(type="input_text",text="Describe the visible robot/laboratory scene and relative positions briefly, using image evidence only. Do not invent coordinates." if real_image else "Name the color of the left half, then the right half. Two words only."),dict(type="input_image",image_url=real_image or color_png(),detail="low")])]
            elif capability=="tools":items=[dict(role="user",content="Call probe_echo with value17. Do not answer in prose.")];extra=dict(tools=tools,tool_choice={"type":"function","name":"probe_echo"})
            elif capability=="structured":
                items=[dict(role="user",content="Return the capability word ready and integer17 in the requested schema.")]
                extra=dict(text={"format":{"type":"json_schema","name":"probe_result","strict":True,"schema":{"type":"object","properties":{"capability":{"type":"string"},"value":{"type":"integer"}},"required":["capability","value"],"additionalProperties":False}}})
            elif capability=="multiturn":
                if last_tool_response is None:
                    evidence["probes"][capability]={"ok":False,"status":"TOOL_PROBE_REQUIRED"};continue
                call=response_tools(last_tool_response)[0]
                items=[dict(role="user",content="Call probe_echo with value17."),*last_tool_response["output"],dict(type="function_call_output",call_id=call["call_id"],output=json.dumps({"echoed":17})),dict(role="user",content="What integer did the tool return? Reply with the integer only.")]
            else:
                # Invalid parameter, not a model substitution, checks error safety.
                items=[dict(role="user",content="Reply OK.")];extra=dict(temperature=-999)
            response,meta=client.responses(items,instructions=instruction,label="probe:"+capability,**extra)
            text=response_text(response);calls=response_tools(response)
            ok=("LABSIM_PROBE_OK" in text if capability=="text" else
                (len(text.strip())>=20 if real_image else "red" in text.lower() and "blue" in text.lower()) if capability=="image" else
                bool(calls and calls[0]["name"]=="probe_echo" and calls[0]["arguments"]=={"value":17}) if capability=="tools" else
                (json.loads(text)=={"capability":"ready","value":17}) if capability=="structured" else
                "17" in text if capability=="multiturn" else False)
            evidence["probes"][capability]=dict(ok=ok,status="COMPLETED",requested_model=cfg["model"],returned_model=response.get("model"),response_id=response.get("id"),usage=response.get("usage"),output_text=text[:500],tool_calls=calls,request_id=meta["request_id"],wall_seconds=meta["wall_seconds"])
            evidence["responses_supported"]=True
            if capability=="tools" and ok:last_tool_response=response
        except (ProviderError,ValueError) as error:
            status=getattr(error,"code","PROTOCOL_INVALID_PROBE_RESPONSE")
            http_status=getattr(error,"status",None)
            demonstrated_api_rejection=capability=="error" and http_status in [400,422]
            evidence["probes"][capability]=dict(ok=demonstrated_api_rejection,status=status,http_status=http_status,
                api_parameter_rejection_demonstrated=demonstrated_api_rejection,
                timeout_observed='TIMEOUT' in status,rate_limit_observed=http_status==429)
            if getattr(error,"status",None) in [404,405,501]:evidence["responses_supported"]=False
        (output/"capabilities.json").write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+"\n")
        print(json.dumps({"capability":capability,**evidence["probes"][capability]},ensure_ascii=False),flush=True)
    evidence["budget"]=client.ledger.summary()
    (output/"capabilities.json").write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+"\n")
    return 0 if all(v["ok"] for v in evidence["probes"].values()) else 2


if __name__=="__main__":raise SystemExit(main())
