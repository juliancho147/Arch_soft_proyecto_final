import sys, json
for d in sorted(json.load(sys.stdin)["items"], key=lambda x: x["metadata"]["name"]):
    c = d["spec"]["template"]["spec"]["containers"][0]["resources"]
    print(f'| {d["metadata"]["name"]} | {d["spec"]["replicas"]} | {c["requests"]["cpu"]} / {c["limits"]["cpu"]} | {c["requests"]["memory"]} / {c["limits"]["memory"]} |')
