import json
import sys
from core.creador_de_tareas import mcp_callables_adapter as m

if len(sys.argv) < 2:
    print("Uso: python get_network_request_dump.py <reqid>")
    sys.exit(2)

reqid = int(sys.argv[1])
out = m.get_network_request(reqid)
print(json.dumps(out, indent=2, ensure_ascii=False))