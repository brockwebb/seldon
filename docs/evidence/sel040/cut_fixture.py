"""Cut SEL-040's HB-189 fixture: the session's last model turns, its 10 api_retry records, the synthetic API error,
its result record. Content is elided (no tool output, no thinking, no prompt text); structure, timestamps, usage,
retry fields and the CLI's own error text are kept verbatim."""
import json
import os
import sys

d = "/Users/brock/GitHub/hazbrief-mcp/logs/dispatch/"
f = [x for x in os.listdir(d) if "HB-189" in x][0]
lines = open(d + f, encoding="utf-8", errors="replace").read().splitlines()
first, last = 3725, 3746          # 0-based: the last user turn before the cut .. the session's result record
out = []
for ln in lines[first:last + 1]:
    o = json.loads(ln)
    t = o.get("type")
    if t == "system" and o.get("subtype") == "thinking_tokens":
        continue
    if t == "system":
        keep = {k: o.get(k) for k in ("type", "subtype", "attempt", "max_retries", "retry_delay_ms", "error_status",
                                      "error")}
    elif t == "assistant":
        m = o["message"]
        content = []
        for c in m.get("content") or []:
            if c.get("type") == "text" and m.get("model") == "<synthetic>":
                content.append({"type": "text", "text": c["text"]})
            else:
                content.append({"type": c.get("type"), "elided": True})
        keep = {"type": t, "timestamp": o.get("timestamp"),
                "message": {"id": m.get("id"), "model": m.get("model"), "role": "assistant",
                            "stop_reason": m.get("stop_reason"), "usage": {
                                k: (m.get("usage") or {}).get(k) for k in
                                ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                                 "output_tokens")},
                            "content": content}}
    elif t == "user":
        keep = {"type": t, "timestamp": o.get("timestamp"),
                "message": {"role": "user", "content": [{"type": "tool_result", "elided": True}]}}
    elif t == "result":
        keep = {k: o.get(k) for k in ("type", "subtype", "is_error", "stop_reason", "num_turns")}
        keep["modelUsage"] = {k: {"elided": True} for k in (o.get("modelUsage") or {})}
    else:
        keep = {"type": t, "elided": True}
    out.append(json.dumps(keep))
dest = sys.argv[1]
with open(dest, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + "\n")
print(len(out), "records ->", dest)
