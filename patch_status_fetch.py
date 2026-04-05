import re

with open("main.py", "r") as f:
    content = f.read()

replacement = """                                # Fetch status from postgres if available
                                try:
                                    import pickle
                                    with psycopg.connect(dbos_url) as conn:
                                        with conn.cursor() as cur:
                                            cur.execute("SELECT checkpoint FROM checkpoints WHERE thread_id = %s ORDER BY thread_ts DESC LIMIT 1", (t_id,))
                                            row = cur.fetchone()
                                            if row:
                                                try:
                                                    ckpt = pickle.loads(row[0])
                                                    if "channel_values" in ckpt and "__root__" in ckpt["channel_values"]:
                                                        state = ckpt["channel_values"]["__root__"]
                                                        if isinstance(state, dict):
                                                            status = state.get("status", "IDLE")
                                                except Exception:
                                                    pass
                                except Exception:
                                    pass
"""

content = content.replace("""                                # Fetch status from postgres if available
                                try:
                                    with psycopg.connect(dbos_url) as conn:
                                        with conn.cursor() as cur:
                                            cur.execute("SELECT checkpoint FROM checkpoints WHERE thread_id = %s ORDER BY thread_ts DESC LIMIT 1", (t_id,))
                                            row = cur.fetchone()
                                            if row:
                                                # Checkpoint is bytes containing pickled data usually or json.
                                                # To safely read just status without unpickling langgraph state, we can try to find status in the repr, but better to use Graph API if compiled, but graph is compiled per project.
                                                # We can just instantiate a generic graph or parse if we can.
                                                # For now, let's just attempt to see if it's there or use a simplified approach:
                                                # Actually, LangGraph stores checkpoints. We will fetch status via graph if we compile it.
                                                pass
                                except Exception:
                                    pass""", replacement)

with open("main.py", "w") as f:
    f.write(content)
